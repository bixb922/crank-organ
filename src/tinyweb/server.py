"""
Tiny Web - pretty simple and powerful web server for tiny platforms like ESP8266 / ESP32
MIT license
(C) Konstantin Belyalov 2017-2018
"""
# Changed import logging to minilog
import minilog 
import asyncio
import uasyncio.core
import ujson as json
import gc
import uos as os
import sys
import uerrno as errno
import usocket as socket
import time # Changed: log time and profile
import scheduler 
import config

# Changed:
# Added minilog logger
# Call garbage collector less frequently if large RAM (e.g. 8MB)
# Add caddr support in request
# Yield CPU frequently to aid asyncio respone

log = minilog.getLogger("tinyweb")

# Changed:
if config.large_memory:
	garbage_collect = lambda : None
else:
	garbage_collect = gc.collect

type_gen = type((lambda: (yield))())

#Changed: Added to do a bit of profiling
t0 = time.ticks_ms()
def mide_tiempo(s):
    return # Profiler DISABLED
    global t0
    t1 = time.ticks_ms()
    if s != "":
        dt = time.ticks_diff(t1,t0)
        print(f"tinyweb {s} {dt}")
    t0 = t1
mide_tiempo("")
mide_tiempo("partida")

# uasyncio v3 is shipped with MicroPython 1.13, and contains some subtle
# but breaking changes. See also https://github.com/peterhinch/micropython-async/blob/master/v3/README.md
IS_UASYNCIO_V3 = hasattr(asyncio, "__version__") and asyncio.__version__ >= (3,)

@micropython.native
def urldecode_plus(s):
    """Decode urlencoded string (including '+' char).

    Returns decoded string
    """
    s = s.replace('+', ' ')
    arr = s.split('%')
    res = arr[0]
    for it in arr[1:]:
        if len(it) >= 2:
            res += chr(int(it[:2], 16)) + it[2:]
        elif len(it) == 0:
            res += '%'
        else:
            res += it
    return res


@micropython.native
def parse_query_string(s):
    """Parse urlencoded string into dict.

    Returns dict
    """
    res = {}
    pairs = s.split('&')
    for p in pairs:
        vals = [urldecode_plus(x) for x in p.split('=', 1)]
        if len(vals) == 1:
            res[vals[0]] = ''
        else:
            res[vals[0]] = vals[1]
    return res


class HTTPException(Exception):
    """HTTP protocol exceptions"""

    def __init__(self, code=400):
        self.code = code


class request:
    """HTTP Request class"""

    def __init__(self, _reader, _caddr):
        self.reader = _reader
        self.headers = {}
        self.method = b''
        self.path = b''
        self.query_string = b''
        # Changed: request now has caddr
        self.caddr = _caddr

    @micropython.native
    async def read_request_line(self):
        mide_tiempo("read_request_line 1")
        """Read and parse first line (AKA HTTP Request Line).
        Function is generator.

        Request line is something like:
        GET /something/script?param1=val1 HTTP/1.1
        """
        while True:
            await asyncio.sleep_ms(1) # Changed: yield control to asyncio
            rl = await self.reader.readline()
            await asyncio.sleep_ms(1) # Changed: yield control to asyncio
            mide_tiempo("read_request_line 2 read line")
            # skip empty lines
            if rl == b'\r\n' or rl == b'\n':
                continue
            break
        rl_frags = rl.split()
        if len(rl_frags) != 3:
            raise HTTPException(400)
        self.method = rl_frags[0]
        url_frags = rl_frags[1].split(b'?', 1)
        self.path = url_frags[0]
        if len(url_frags) > 1:
            self.query_string = url_frags[1]
        mide_tiempo("read_request_line fin")
       

    @micropython.native
    async def read_headers(self, save_headers=[]):
        """Read and parse HTTP headers until \r\n\r\n:
        Optional argument 'save_headers' controls which headers to save.
            This is done mostly to deal with memory constrains.

        Function is generator.

        HTTP headers could be like:
        Host: google.com
        Content-Type: blah
        \r\n
        """
        # Changed:
		# This loop consumes 10-15 millisec for each of the about
		# 8 headers of a request = 120 millisec.
		# This is the most CPU consuming component 
		# of a simple request.
        while True:
            garbage_collect()

            await asyncio.sleep_ms(1) # Changed: yield control to asyncio
            line = await self.reader.readline()
            await asyncio.sleep_ms(1) # Changed: yield control to asyncio

            mide_tiempo("read_headers 1")
            if line == b'\r\n':
                break
            frags = line.split(b':', 1)
            if len(frags) != 2:
                raise HTTPException(400)
            if frags[0] in save_headers:
                self.headers[frags[0]] = frags[1].strip()
            mide_tiempo("read_headers 2")
           
            

    async def read_parse_form_data(self):
        """Read HTTP form data (payload), if any.
        Function is generator.

        Returns:
            - dict of key / value pairs
            - None in case of no form data present
        """
        # TODO: Probably there is better solution how to handle
        # request body, at least for simple urlencoded forms - by processing
        # chunks instead of accumulating payload.
        garbage_collect()
        if b'Content-Length' not in self.headers:
            return {}
        # Parse payload depending on content type
        if b'Content-Type' not in self.headers:
            # Unknown content type, return unparsed, raw data
            return {}
        size = int(self.headers[b'Content-Length'])
        if size > self.params['max_body_size'] or size < 0:
            raise HTTPException(413)
        data = await self.reader.readexactly(size)
   
        # Use only string before ';', e.g:
        # application/x-www-form-urlencoded; charset=UTF-8
        ct = self.headers[b'Content-Type'].split(b';', 1)[0]
        
        try:
            if ct == b'application/json':
                return json.loads(data)
            elif ct == b'application/x-www-form-urlencoded':
                return parse_query_string(data.decode())
        except ValueError:
            # Re-generate exception for malformed form data
            raise HTTPException(400)


class response:
    """HTTP Response class"""

    def __init__(self, _writer):
        self.writer = _writer
        self.send = _writer.awrite
        self.code = 200
        self.version = '1.0'
        self.headers = {}

    async def _send_headers(self):
        """Compose and send:
        - HTTP request line
        - HTTP headers following by \r\n.
        This function is generator.

        P.S.
        Because of usually we have only a few HTTP headers (2-5) it doesn't make sense
        to send them separately - sometimes it could increase latency.
        So combining headers together and send them as single "packet".
        """
        mide_tiempo("send_headers 1")
       
        # Request line
        hdrs = 'HTTP/{} {} MSG\r\n'.format(self.version, self.code)
        # Headers
        for k, v in self.headers.items():
            hdrs += '{}: {}\r\n'.format(k, v)
        hdrs += '\r\n'
        # Collect garbage after small mallocs
        garbage_collect()
        await self.send(hdrs)
        await asyncio.sleep_ms(1) # Changed: yield CPU frequently
        mide_tiempo("send_headers 2")
       

    async def error(self, code, msg=None):
        """Generate HTTP error response
        This function is generator.

        Arguments:
            code - HTTP response code

        Example:
            # Not enough permissions. Send HTTP 403 - Forbidden
            await resp.error(403)
        """
        self.code = code
        if msg:
            self.add_header('Content-Length', len(msg))
        await self._send_headers()
        if msg:
            await self.send(msg)

    async def redirect(self, location, msg=None):
        """Generate HTTP redirect response to 'location'.
        Basically it will generate HTTP 302 with 'Location' header

        Arguments:
            location - URL to redirect to

        Example:
            # Redirect to /something
            await resp.redirect('/something')
        """
        self.code = 302
        self.add_header('Location', location)
        if msg:
            self.add_header('Content-Length', len(msg))
        await self._send_headers()
        if msg:
            await self.send(msg)

    def add_header(self, key, value):
        """Add HTTP response header

        Arguments:
            key - header name
            value - header value

        Example:
            resp.add_header('Content-Encoding', 'gzip')
        """
        self.headers[key] = value

    def add_access_control_headers(self):
        """Add Access Control related HTTP response headers.
        This is required when working with RestApi (JSON requests)
        """
        self.add_header('Access-Control-Allow-Origin', self.params['allowed_access_control_origins'])
        self.add_header('Access-Control-Allow-Methods', self.params['allowed_access_control_methods'])
        self.add_header('Access-Control-Allow-Headers', self.params['allowed_access_control_headers'])

    async def start_html(self):
        """Start response with HTML content type.
        This function is generator.

        Example:
            await resp.start_html()
            await resp.send('<html><h1>Hello, world!</h1></html>')
        """
        self.add_header('Content-Type', 'text/html; charset=UTF-8')
        await self._send_headers()

    async def send_file(self, filename, content_type=None, content_encoding=None, max_age=2592000, buf_size=1024):
        """Send local file as HTTP response.
        This function is generator.

        Arguments:
            filename - Name of file which exists in local filesystem
        Keyword arguments:
            content_type - Filetype. By default - None means auto-detect.
            max_age - Cache control. How long browser can keep this file on disk.
                      By default - 30 days
                      Set to 0 - to disable caching.

        Example 1: Default use case:
            await resp.send_file('images/cat.jpg')

        Example 2: Disable caching:
            await resp.send_file('static/index.html', max_age=0)

        Example 3: Override content type:
            await resp.send_file('static/file.bin', content_type='application/octet-stream')
        """
        mide_tiempo("send_file 1")
        try:
            # Get file size
            stat = os.stat(filename)
            slen = str(stat[6])
            self.add_header('Content-Length', slen)
            # Find content type
            if content_type:
                self.add_header('Content-Type', content_type)
            # Add content-encoding, if any
            if content_encoding:
                self.add_header('Content-Encoding', content_encoding)
            # Since this is static content is totally make sense
            # to tell browser to cache it, however, you can always
            # override it by setting max_age to zero
            self.add_header('Cache-Control', 'max-age={}, public'.format(max_age))
            
            with open(filename, "rb") as f:
                mide_tiempo("send_file 2")
               
                await self._send_headers()
                mide_tiempo("send_file 3")
                garbage_collect()
               
                buf = bytearray(min(stat[6], buf_size))
                while True:
                    size = f.readinto(buf)
                    if size == 0:
                        break
                    await self.send(buf, sz=size)
                    mide_tiempo("send_file 4 after send")
                    await asyncio.sleep_ms(1)
                    
        except OSError as e:
            # special handling for ENOENT / EACCESS
            if e.args[0] in (errno.ENOENT, errno.EACCES):
                raise HTTPException(404)
            else:
                raise
        mide_tiempo("send_file 5")


async def restful_resource_handler(req, resp, param=None):
    print("restful_resource_handler called")
    """Handler for RESTful API endpoins"""
    # Gather data - query string, JSON in request body...
    data = await req.read_parse_form_data()
    # Add parameters from URI query string as well
    # This one is actually for simply development of RestAPI
    if req.query_string != b'':
        data.update(parse_query_string(req.query_string.decode()))
    # Call actual handler
    _handler, _kwargs = req.params['_callmap'][req.method]
    # Collect garbage before / after handler execution
    garbage_collect()
    if param:
        res = _handler(data, param, **_kwargs)
    else:
        res = _handler(data, **_kwargs)
	garbage_collect()
    # Handler result could be:
    # 1. generator - in case of large payload
    # 2. string - just string :)
    # 2. dict - meaning client what tinyweb to convert it to JSON
    # it can also return error code together with str / dict
    # res = {'blah': 'blah'}
    # res = {'blah': 'blah'}, 201
    if isinstance(res, type_gen):
        # Result is generator, use chunked response
        # NOTICE: HTTP 1.0 by itself does not support chunked responses, so, making workaround:
        # Response is HTTP/1.1 with Connection: close
        resp.version = '1.1'
        resp.add_header('Connection', 'close')
        resp.add_header('Content-Type', 'application/json')
        resp.add_header('Transfer-Encoding', 'chunked')
        resp.add_access_control_headers()
        await resp._send_headers()
        # Drain generator
        for chunk in res:
            chunk_len = len(chunk.encode('utf-8'))
            await resp.send('{:x}\r\n'.format(chunk_len))
            await resp.send(chunk)
            await resp.send('\r\n')
            garbage_collect()
        await resp.send('0\r\n\r\n')
    else:
        if type(res) == tuple:
            resp.code = res[1]
            res = res[0]
        elif res is None:
            raise Exception('Result expected')
        # Send response
        if type(res) is dict:
            res_str = json.dumps(res)
        else:
            res_str = res
        resp.add_header('Content-Type', 'application/json')
        resp.add_header('Content-Length', str(len(res_str)))
        resp.add_access_control_headers()
        await resp._send_headers()
        await resp.send(res_str)


class webserver:

    def __init__(self, request_timeout=3, max_concurrency=3, backlog=16, debug=False):
        """Tiny Web Server class.
        Keyword arguments:
            request_timeout - Time for client to send complete request
                              after that connection will be closed.
            max_concurrency - How many connections can be processed concurrently.
                              It is very important to limit this number because of
                              memory constrain.
                              Default value depends on platform
            backlog         - Parameter to socket.listen() function. Defines size of
                              pending to be accepted connections queue.
                              Must be greater than max_concurrency
            debug           - Whether send exception info (text + backtrace)
                              to client together with HTTP 500 or not.
        """
        self.loop = asyncio.get_event_loop()
        self.request_timeout = request_timeout
        self.max_concurrency = max_concurrency
        self.backlog = backlog
        self.debug = debug
        self.explicit_url_map = {}
        self.catch_all_handler = None
        self.parameterized_url_map = {}
        # Currently opened connections
        # self.conns = {} # HVB ya no se usa
        # Statistics
        self.processed_connections = 0

    def _find_url_handler(self, req):
        """Helper to find URL handler.
        Returns tuple of (function, opts, param) or (None, None) if not found.
        """

        # First try - lookup in explicit (non parameterized URLs)
        if req.path in self.explicit_url_map:
            return self.explicit_url_map[req.path]
        # Second try - strip last path segment and lookup in another map
        idx = req.path.rfind(b'/') + 1
        path2 = req.path[:idx]
        if len(path2) > 0 and path2 in self.parameterized_url_map:
            # Save parameter into request
            req._param = req.path[idx:].decode()
            return self.parameterized_url_map[path2]

        if self.catch_all_handler:
            return self.catch_all_handler

        # No handler found
        return (None, None)

    async def _handle_request(self, req, resp):
        mide_tiempo("_handle_request 1")
       

        await req.read_request_line()
        req.t0 = time.ticks_ms() # Changed: added to show request time
        mide_tiempo("_handle_request 2")
       
      

        # Find URL handler
        req.handler, req.params = self._find_url_handler(req)
        if not req.handler:
            # No URL handler found - read response and issue HTTP 404
            await req.read_headers()
            raise HTTPException(404)
        mide_tiempo("_handle_request 3")
       
        
        # req.params = params
        # req.handler = han
        resp.params = req.params
        # Read / parse headers
        await req.read_headers(req.params['save_headers'])
        mide_tiempo("_handle_request 4")
       
        
    # Changed: Added caddr support

    async def _handler(self, reader, writer, caddr):
        mide_tiempo("_handler 1")
       

        """Handler for TCP connection with
        HTTP/1.0 protocol implementation
        """
        garbage_collect()

        try:
            mide_tiempo("_handler 2")
            req = request(reader,caddr)
            mide_tiempo("_handler 3")
           
            resp = response(writer)
            mide_tiempo("_handler 4")
            # Read HTTP Request with timeout
           
            
            await asyncio.wait_for(self._handle_request(req, resp),
                                   self.request_timeout)
            mide_tiempo("_handler 5")
            # OPTIONS method is handled automatically
            if req.method == b'OPTIONS':
                resp.add_access_control_headers()
                # Since we support only HTTP 1.0 - it is important
                # to tell browser that there is no payload expected
                # otherwise some webkit based browsers (Chrome)
                # treat this behavior as an error
                resp.add_header('Content-Length', '0')
                mide_tiempo("_handler 6")
                await resp._send_headers()
                mide_tiempo("_handler 7")
                return
           


            # Ensure that HTTP method is allowed for this path
            
            if req.method not in req.params['methods']:
                raise HTTPException(405)
            mide_tiempo("_handler 8")


            # Handle URL
            garbage_collect()
           
            mide_tiempo("_handler 9")
            if hasattr(req, '_param'):
                await req.handler(req, resp, req._param)
            else:
                await req.handler(req, resp)
            mide_tiempo("_handler 10")
            
            # Done here
            # Changed: log total request time
            dt = time.ticks_diff( time.ticks_ms(), req.t0 )
            log.debug(f"{req.path.decode()} {dt} msec") 
            mide_tiempo("_handler 11")

        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        except OSError as e:
            # Do not send response for connection related errors - too late :)
            # P.S. code 32 - is possible BROKEN PIPE error (TODO: is it true?)
            if e.args[0] not in (errno.ECONNABORTED, errno.ECONNRESET, 32):
                try:
                    await resp.error(500)
                except Exception as e:
                    log.exc(e, "")
        except HTTPException as e:
            try:
                await resp.error(e.code)
            except Exception as e:
                log.exc(e, "")
        except Exception as e:
            # Unhandled expection in user's method
            log.error(req.path.decode())
            log.exc(e, "")
            try:
                await resp.error(500)
                # Send exception info if desired
                if self.debug:
                    sys.print_exception(e, resp.writer.s)
            except Exception as e:
                pass
        finally:
            mide_tiempo("_handler 12")
            writer.close()
            await writer.wait_closed()
            mide_tiempo("_handler 13")

    def add_route(self, url, f, **kwargs):
        mide_tiempo("add_route 1")

        """Add URL to function mapping.

        Arguments:
            url - url to map function with
            f - function to map

        Keyword arguments:
            methods - list of allowed methods. Defaults to ['GET', 'POST']
            save_headers - contains list of HTTP headers to be saved. Case sensitive. Default - empty.
            max_body_size - Max HTTP body size (e.g. POST form data). Defaults to 1024
            allowed_access_control_headers - Default value for the same name header. Defaults to *
            allowed_access_control_origins - Default value for the same name header. Defaults to *
        """
        if url == '' or '?' in url:
            raise ValueError('Invalid URL')
        # Initial params for route
        params = {'methods': ['GET'],
                  'save_headers': [],
                  'max_body_size': 1024,
                  'allowed_access_control_headers': '*',
                  'allowed_access_control_origins': '*',
                  }
        params.update(kwargs)
        params['allowed_access_control_methods'] = ', '.join(params['methods'])
        # Convert methods/headers to bytestring
        params['methods'] = [x.encode() for x in params['methods']]
        params['save_headers'] = [x.encode() for x in params['save_headers']]
        # If URL has a parameter
        if url.endswith('>'):
            idx = url.rfind('<')
            path = url[:idx]
            idx += 1
            param = url[idx:-1]
            if path.encode() in self.parameterized_url_map:
                raise ValueError('URL exists')
            params['_param_name'] = param
            self.parameterized_url_map[path.encode()] = (f, params)

        if url.encode() in self.explicit_url_map:
            raise ValueError('URL exists')
        self.explicit_url_map[url.encode()] = (f, params)
        mide_tiempo("add_route 2")

    def add_resource(self, cls, url, **kwargs):
        """Map resource (RestAPI) to URL

        Arguments:
            cls - Resource class to map to
            url - url to map to class
            kwargs - User defined key args to pass to the handler.

        Example:
            class myres():
                def get(self, data):
                    return {'hello': 'world'}


            app.add_resource(myres, '/api/myres')
        """
        methods = []
        callmap = {}
        # Create instance of resource handler, if passed as just class (not instance)
        try:
            obj = cls()
        except TypeError:
            obj = cls
        # Get all implemented HTTP methods and make callmap
        for m in ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']:
            fn = m.lower()
            if hasattr(obj, fn):
                methods.append(m)
                callmap[m.encode()] = (getattr(obj, fn), kwargs)
        self.add_route(url, restful_resource_handler,
                        methods=methods,
                       save_headers=['Content-Length', 'Content-Type'],
                       _callmap=callmap)

    def catchall(self):
        """Decorator for catchall()

        Example:
            @app.catchall()
            def catchall_handler(req, resp):
                response.code = 404
                await response.start_html()
                await response.send('<html><body><h1>My custom 404!</h1></html>\n')
        """
        params = {'methods': [b'GET'], 'save_headers': [], 'max_body_size': 1024, 'allowed_access_control_headers': '*', 'allowed_access_control_origins': '*'}

        def _route(f):
            self.catch_all_handler = (f, params)
            return f
        return _route

    def route(self, url, **kwargs):
        """Decorator for add_route()

        Example:
            @app.route('/')
            def index(req, resp):
                await resp.start_html()
                await resp.send('<html><body><h1>Hello, world!</h1></html>\n')
        """
        def _route(f):
            self.add_route(url, f, **kwargs)
            return f
        return _route

    def resource(self, url, method='GET', **kwargs):
        """Decorator for add_resource() method

        Examples:
            @app.resource('/users')
            def users(data):
                return {'a': 1}

            @app.resource('/messages/<topic_id>')
            async def index(data, topic_id):
                yield '{'
                yield '"topic_id": "{}",'.format(topic_id)
                yield '"message": "test",'
                yield '}'
        """
        def _resource(f):
            self.add_route(url, restful_resource_handler,
                           methods=[method],
                           save_headers=['Content-Length', 'Content-Type'],
                           _callmap={method.encode(): (f, kwargs)})
            return f
        return _resource

    async def _server_callback(self, reader, writer):
        # HVB Reescrito
        # Get ( client ip, port )
        caddr = writer.get_extra_info("peername") 
        try:
            await self._handler(reader,writer, caddr)
        except asyncio.CancelledError:
            return
        finally:
            try: # ignore errors when draining
                await writer.drain()
                writer.close()
                await writer.wait_closed()
            except Exception as e:
                log.error(f"Recoverable exception in webserver/drain {e}")
                pass
            
    async def run(self, host="127.0.0.1", port=8081 ):
        """Run Web Server. By default it runs forever.

        Keyword arguments:
            host - host to listen on. By default - localhost (127.0.0.1)
            port - port to listen on. By default - 8081
        """
        # HVB reescrito
        # asyncio.start_server returns after a very short time
        self.tcp_server = await asyncio.start_server( self._server_callback, host, port )
            
    async def shutdown(self):
        """Gracefully shutdown Web Server"""
        # HVB reescrito
        self.tcp_server.close()
        await self.tcp_server.wait_closed()
        log.info("webserver shutdown complete")
        
# start this on     