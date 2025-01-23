# (c) 2024 Hermann von Borries
# MIT License

class Matrix:
    def __init__( self, rows=0, columns=0 ):
        self.rows = rows
        self.columns = columns
        self.elements = [ [0]*columns for _ in range(rows) ]

    def setElements( self, new_values):
        # use: m = Matrix().setElements( list of lists )
        self.rows = len(new_values)
        self.columns = len(new_values[0])
        self.elements = []
        for i in range(self.rows):
            assert len(new_values[i]) == self.columns
            self.elements.append( list( new_values[i] ) )
        return self
    
    def print( self ):
        for row in range(self.rows):
            for column in range(self.columns):
                print(f"{self.elements[row][column]:7.3f}", end="")
            print("")
    
    def inverse(self):
        # Returns matrix inverse
        assert self.rows == self.columns
        tmp = Matrix(self.rows, self.columns*2)
        for row in range(self.rows):
            tmp.elements[row][0:self.columns] = self.elements[row]
            tmp.elements[row][row+self.columns] = 1
        tmp._gaussReduce()
        inv = Matrix(self.rows, self.columns)
        for row in range(self.rows):
            inv.elements[row] = tmp.elements[row][self.columns:]
        return inv

    def _gaussReduce( self ):
        row = 0
        lead = 0
        while True:
            if not( row < self.rows and lead < self.columns ):
                break
            i = row
            while self.elements[i][lead] == 0:
                i += 1
                if i == self.rows:
                    i = row
                    lead += 1
                    if lead == self.columns:
                        return
            self._swapRows( i, row )
            if self.elements[row][lead] != 0:
                f = self.elements[row][lead]
                for column in range(self.columns):
                    self.elements[row][column] /= f  # type:ignore
            for j in range(self.rows):
                if j == row:
                    continue
                f = self.elements[j][lead]
                for column in range(self.columns):
                    self.elements[j][column] -= f * self.elements[row][column]
            row += 1
            lead += 1

    def __mul__( a, b ):  # type:ignore
        # Matrix multiply, returns a*b
        assert a.columns == b.rows
        result = Matrix( a.rows, b.columns )
        for i in range(a.rows):
            resultRow = result.elements[i]
            aRow = a.elements[i]
            for j in range(a.columns):
                bRow = b.elements[j]
                for k in range(b.columns):
                    resultRow[k] += aRow[j] * bRow[k]
        return result
    
    def transpose( self ):
        # Returns matrix transposed
        result = Matrix( self.columns, self.rows )
        for i in range(self.rows):
            for j in range(self.columns):
                result.elements[j][i] = self.elements[i][j]
        return result

    def _swapRows(self,i,j):
        tmp = self.elements[i]
        self.elements[i] = self.elements[j]
        self.elements[j] = tmp

def linear_regression(X, y):
    # Takes 6 msec on ESP32 for 3x15 Matrix
    XT = X.transpose()
    return  y*XT*(X*XT).inverse()
