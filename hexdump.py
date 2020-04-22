class HexDump:
    def __init__(self, block, len_row, start):
        self.block = block
        self.k = start
        self.lr = len_row
        self.build()

    def build(self):
        self.lines = []
        rows = len(self.block) // self.lr + min(len(self.block) % self.lr, 1)
        for n in range(rows):
            self.lines.append(self.get_line(n * self.lr))

# ---------------------------------------------------------------------#

    def get_line(self, n):
        result = []
        result.append(self.get_begin(n))
        for i in range(n, n + self.lr):
            try:
                hexed_byte = "0" + hex(self.block[i])[2:]
            except IndexError:
                hexed_byte = " " * 3
            result.append("{} ".format(hexed_byte[-2:]))
        result.append(self.get_end(n))
        return ''.join(result)

    def get_end(self, n):
        result = ["| "]
        for i in range(n, self.lr + n):
            if i < len(self.block):
                if self.block[i] in range(32, 127):
                    result.append(chr(self.block[i]))
                else:
                    result.append(".")
            else:
                result.append(" ")
        return ''.join(result)

    def get_begin(self, n):
        return " {} | ".format(("0" * 8 + hex(n+self.k)[2:])[-8:])
