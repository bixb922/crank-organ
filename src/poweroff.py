# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License

# Power off task. Monitors activity and enters deepsleep to save battery
# if not active.
import machine
import asyncio

from drehorgel import config, led, setlist, controller, player
from minilog import getLogger

class PowerManager:
    def __init__(self):
        self.logger = getLogger(__name__)
        self.power_task = asyncio.create_task(self._power_process())
        self.logger.debug("init ok")

    async def _power_process(self):
        last_tune = None
        last_playtime = None
        idle_minutes = 0
        idle_deepsleep_minutes = config.idle_deepsleep_minutes
        if idle_deepsleep_minutes <= 0:
            return
        await asyncio.sleep_ms(1000)
        from webserver import is_active
        while True:
            await asyncio.sleep(60)  # Sleep for 1 minute and check.
            progress = player.get_progress()
            playtime = progress["playtime"]
            # no player, no progress, no change of playtime

            tune = progress["tune"]
            # Any activity in the last minute?
            if (
                playtime != last_playtime
                or tune != last_tune
                or is_active()
            ):
                # Yes, reset time
                idle_minutes = 0
            else:
                idle_minutes += 1
                self.logger.debug( f"Idle for {idle_minutes} minutes limit {idle_deepsleep_minutes}" )

            last_tune = tune
            last_playtime = playtime

            if idle_minutes > idle_deepsleep_minutes:
                self.logger.info(
                    f"Idle for {idle_minutes} minutes, entering deepsleep"
                )
                led.ack()
                await self.wait_and_power_off()
                # Not to return
            progress = None
            tune = None
            playtime = None
            
    async def _wait_and_action(self, action):
        setlist.stop_tune()
        controller.all_notes_off()
        led.shutdown()
        # Wait for web server to respond, led to flash, etc
        # Don't shut down microdot, need it to respond.
        await asyncio.sleep_ms(1000)
        action()
 
    async def wait_and_power_off(self):
        # Deepsleep is the closest thing to "self power off"
        # Could not make wake_on_touch work here.
        # >>>must find root cause, but deepsleep leaves some GPIO (GPIO 11) on.
        # >>> (this is a hardware problem)
        await self._wait_and_action( machine.deepsleep )
        # Does not return
        # await self._wait_and_action( self.lowpower )

    # def lowpower(self):
    #     import network, time
    #     sta_if = network.WLAN(network.STA_IF)
    #     sta_if.active(False)
    #     machine.freq(40_000_000)
    #     while True:
    #         time.sleep_ms(5_000)
    #         led.on( (1,1,1))
    #         time.sleep_ms(20)
    #         led.off()


    async def wait_and_reset(self):
        await self._wait_and_action( machine.reset )
        # Does not return


