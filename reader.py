from enum import Enum
from datetime import datetime
from os import path


class Type(Enum):
    dir_ = 1
    file_ = 2


class MyFile:
    def __init__(self, name, n, typ, time, date, size, blocks):
        self.name = name
        self.start = n
        self.type = typ
        self.time = time
        self.date = date
        self.size = size
        self.blocks = blocks

    def __str__(self):
        return self.name

    def get_line(self, fn):
        t = "d" if self.type == Type.dir_ else "f"
        date, time, size = (self.date, self.time, self.size)
        size = (" "*10+str(size))[-10:]
        return "{}  {}  {}  {}  {}".format(date, time, t, size, fn)


class BigDataForClusterError(Exception):
    def __str__(self):
        return "Illigal length of data for cluster"


class BrokenFATError(Exception):
    def __str__(self):
        return "Broken FAT system area"


class FreeSpaceError(OSError):
    def __str__(self):
        return "No free space left in image"


class FileExistsError(OSError):
    def __init__(self, fn):
        self.name = fn
        super().__init__()

    def __str__(self):
        return "{}: file already exists".format(self.name)


class NotADirectoryError(OSError):
    def __init__(self, fn):
        self.name = fn
        super().__init__()

    def __str__(self):
        return "{}: is not a directory".format(self.name)


class CrossedCluster(Exception):
    def __init__(self, cluster):
        self.cluster = cluster
        super().__init__()

    def __str__(self):
        return "Crossed cluster {}".format(self.cluster)


class LostedCluster(Exception):
    def __init__(self, cluster):
        self.cluster = cluster
        super().__init__()

    def __str__(self):
        return "Losted cluster {}".format(self.cluster)


class NonZeroDirSize(Exception):
    def __init__(self, dn):
        self.dn = dn
        super().__init__()

    def __str__(self):
        return "Non zero size of {} directory".format(self.dn)


class BrokenFileSize(Exception):
    def __init__(self, fn):
        self.fn = fn
        super().__init__()

    def __str__(self):
        return "Wrong count of clusters or size set for {}".format(self.fn)


class WrongDirStruct(Exception):
    def __init__(self, dn):
        self.dn = dn
        super().__init__()

    def __str__(self):
        return "Wrong structure for high level directory {}".format(self.dn)


class AllFATErrors(Exception):
    def __init__(self, errs):
        self.errs = errs
        super().__init__()

    def __str__(self):
        return "\n".join(self.errs)


class PermissionDenied(Exception):
    def __str__(self):
        return "No possibility to write"


def get_bytes(num):
    result = []
    for i in range(4):
        result.append(num % 256)
        num //= 256
    return bytes(result)


def get_date_time():
    dt = datetime.now()
    dt = [dt.second//2, dt.minute, dt.hour, dt.day, dt.month, dt.year-1980]
    sec, minute, hour = map(lambda x: bin(x)[2:], dt[:3])
    time = ('0'*5+hour)[-5:] + ('0'*6+minute)[-6:] + ('0'*5+sec)[-5:]
    time = get_bytes(int(time, 2))[:2]
    day, mon, year = map(lambda x: bin(x)[2:], dt[3:])
    date = ('0'*7+year)[-7:] + ('0'*4+mon)[-4:] + ('0'*5+day)[-5:]
    date = get_bytes(int(date, 2))[:2]
    return (date, time, bytes([datetime.now().microsecond//10000]))


def make_lfn_records(fn, chk_sum):
    result = []
    k = len(fn) // 26
    if k*26 < len(fn):
        fn += b'\x00\x00' + b'\xff'*((k+1)*26 - len(fn)-2)
    k = 0
    while fn:
        data, k = ([], k+1)
        data.append(bytes([k]))
        data.append(fn[:10])
        fn = fn[10:]
        data.append(b'\x0f\x00')
        data.append(bytes([chk_sum]))
        data.append(fn[:12])
        fn = fn[12:]
        data.append(b'\x00\x00')
        data.append(fn[:4])
        fn = fn[4:]
        if not fn:
            n = len(data)-7
            data.insert(n, bytes([data.pop(n)[0]+0x40]))
        result.insert(0, b''.join(data))
    return b''.join(result)


class Reader:
    def __init__(self, fn):
        try:
            self.fo, self.writable = (open(fn, 'rb+'), True)
        except Exception:
            self.fo, self.writable = (open(fn, 'rb'), False)
        self.fn = fn
        self.fo.seek(0x0b)
        data = list(map(lambda x: self.read_num(x), [2, 1, 2, 1]))
        for peace in data:
            if not peace:
                raise BrokenFATError
        self.b_per_sec, self.sec_per_clus, res_sec, self.n_of_fats = data
        self.fo.seek(0x24)
        self.sec_per_fat = self.read_num(2)
        if not self.sec_per_fat:
            raise BrokenFATError
        self.start_fat = res_sec*self.b_per_sec
        self.len_fat = self.sec_per_fat*self.b_per_sec
        self.root_dir = self.n_of_fats*self.len_fat+self.start_fat
        self.len_clus = self.sec_per_clus*self.b_per_sec
        date_time = ("00:00:00", "01.01.1980")
        self.root = MyFile("root", 2, Type.dir_, *date_time, 0, (0, 0))
        self.current = self.root
        self.cd(self.root)

    def fschk(self):
        errors = []
        visited = self.get_clusters(self.root.start, errors) + [0, 1]
        visited, errors = self.check_crosses(visited)
        for i in range(self.len_fat//4):
            self.fo.seek(self.start_fat+i*4)
            if self.read_num(4) and i not in visited:
                errors.append(str(LostedCluster(i)))
        if errors:
            raise AllFATErrors(errors)

    def check_crosses(self, visited, dir_="/", errors=[]):
        files = self.files
        isrt = len(files) < 2 or (files[0].name, files[1].name) != (".", "..")
        if dir_ != "/":
            if isrt:
                errors.append(str(WrongDirStruct(dir_)))
            files = files[2:]
        for f in files:
            directory = path.join(dir_, f.name)
            clusters = self.get_clusters(f.start, errors)
            size = len(clusters)*self.len_clus
            for c in clusters:
                if c in visited:
                    errors.append(str(CrossedCluster(c)))
                visited.append(c)
            if f.type == Type.dir_:
                if f.size:
                    errors.append(str(NonZeroDirSize(directory)))
                self.cd(f)
                self.check_crosses(visited, directory, errors)
                self.cd(self.files[1])
            elif f.size not in range(size-self.len_clus, size+1):
                errors.append(str(BrokenFileSize(directory)))
        return (visited, errors)

    def md(self, dn, check=True):
        if not self.writable:
            raise PermissionDenied
        if check:
            self.check_double(dn)
        start, cur_start = (self.add_cluster(), self.current.start)
        self.make_new_records(dn, Type.dir_, start)
        data = self.make_dos_record(b'.', Type.dir_, start, 0) +\
            self.make_dos_record(b'..', Type.dir_, cur_start, 0)
        self.write_data(start, data+self.get_data(start)[64:])

    def cf(self, fn, start=0, size=0):
        if not self.writable:
            raise PermissionDenied
        self.check_double(fn)
        self.make_new_records(fn, Type.file_, start, size)

    def check_double(self, fn):
        for f in self.files:
            if f.name == fn:
                raise FileExistsError(fn)

    def cd(self, file_):
        if file_.type != Type.dir_:
            raise NotADirectoryError(file_.name)
        if not file_.start:
            self.cd(self.root)
            return
        self.current = file_
        data = self.get_data(file_.start)
        name, self.files, k = (b'', [], 0)
        for i in range(len(data)//32):
            if k > 0:
                k -= 1
                continue
            block = data[i*32:(i+1)*32]
            if block[0] in [0xe5, 0x00]:
                continue
            while block[0x0b] == 0x0f:
                k += 1
                name = self.parse_record(block)+name
                block = data[(i+k)*32:(i+k+1)*32]
            name = name.decode('utf-16')
            start, typ, time, date, namen, size = self.get_info(block)
            if not name:
                name = namen
            f = MyFile(name, start, typ, time, date, size, (i, k+1))
            self.files.append(f)
            name = b''

    def rm(self, file_):
        if not self.writable:
            raise PermissionDenied
        if file_.type == Type.dir_:
            self.cd(file_)
            for f in self.files:
                if f.name not in "..":
                    self.rm(f)
            self.cd(self.files[1])
        n = file_.start
        while n < 0x0ffffff8 and n:
            start = self.start_fat + n * 4
            self.fo.seek(start)
            n = self.read_num(4)
            self.fo.seek(start)
            self.fo.write(b'\0'*4)
        self.del_dir_record(*file_.blocks)

# -------------------------------------------------------------------- #

    def make_new_records(self, dn, typ, start, size=0):
        dir_name = dn.encode("latin-1") if dn in '..' else b' '
        dos_rec = self.make_dos_record(dir_name, typ, start, size)
        chksum = dos_rec[0]
        for i in range(1, 11):
            chksum = (((chksum & 1) << 7) + (chksum >> 1) + dos_rec[i]) % 256
        data = make_lfn_records(dn.encode('utf-16')[2:], chksum) + dos_rec
        while data:
            data = self.add_entry(data)
            if data:
                last = self.add_cluster(last)

    def find_last_cluster(self, file_):
        n = self.start_fat + file_.start * 4
        self.fo.seek(n)
        s = self.start_fat + self.read_num(4) * 4
        while s < 0x0ffffff8:
            n = s
            self.fo.seek(s)
            s = self.start_fat + self.read_num(4) * 4
        return n

    def get_clusters(self, n, err=None):
        if err is None:
            err = []
        result = []
        while n < 0x0ffffff8 and n > 1:
            result.append(n)
            self.fo.seek(self.start_fat+n*4)
            n = self.read_num(4)
            if n in result:
                err.append(str(CrossedCluster(n)))
                return result
        return result

    def add_cluster(self, end=None):
        self.fo.seek(self.start_fat)
        for n in range(self.len_fat//4):
            if not self.read_num(4):
                if end:
                    self.fo.seek(self.start_fat+end*4)
                    self.fo.write(get_bytes(n))
                self.fo.seek(self.start_fat+n*4)
                self.fo.write(b'\xff'*4)
                self.fo.seek(self.root_dir+(n-2)*self.len_clus)
                self.fo.write(b'\x00'*self.len_clus)
                return n
        raise FreeSpaceError

    def make_dos_record(self, fn, typ, start, size):
        data = []
        start = get_bytes(start)
        dosname = str(len(self.files)).encode('latin-1')
        name, exp = (fn, b'') if fn in b'..' else (dosname[:8], dosname[8:])
        data.append((name+b' '*8)[:8])
        data.append((exp+b' '*3)[:3])
        data.append(b'\x10\x00' if typ == Type.dir_ else b'\x20\x00')
        date, time, ss = get_date_time()
        table_data = [ss, time, date, date, start[2:], time, date, start[:2]]
        for e in table_data:
            data.append(e)
        data.append(get_bytes(size))
        return b''.join(data)

    def get_info(self, block):
        indexes = [0x1a, 0x1b, 0x14, 0x15]
        for i in range(len(indexes)):
            indexes[i] = block[indexes[i]]*(256**i)
        start = sum(indexes)
        typ, n, size = (Type.file_, 0, 0)
        if block[0x0b] & 0x10:
            typ = Type.dir_
        for i in range(0x16, 0x1a):
            n += block[i]*256**(i-0x16)
            size += block[i+6]*256**(i-0x16)
        n = ("0"*32 + bin(n)[2:])[-32:]
        data = [n[16:21], n[21:-5], n[-5:], n[11:16], n[7:11], n[:7]]
        for i in range(len(data)):
            data[i] = int(data[i], 2)
        for i in [0, 1, 3, 4]:
            data[i] = ("00" + str(data[i]))[-2:]
        time = "{}:{}:{}".format(data[0], data[1], ("0"+str(data[2]*2))[-2:])
        date = "{}.{}.{}".format(data[3], data[4], data[5]+1980)
        name = block[:8].decode("latin-1")
        exp = block[8:11].decode("latin-1")
        while name[-1] == " ":
            name = name[:-1]
        if exp != "   ":
            while name[-1] == " ":
                name = name[:-1]
            name = "{}.{}".format(name, exp)
        return (start, typ, time, date, name, size)

    def get_data_by_clusters(self, start):
        clusters = self.get_clusters(start)
        for c in clusters:
            self.fo.seek(self.root_dir+(c-2)*self.len_clus)
            yield self.fo.read(self.len_clus)

    def add_entry(self, data):
        d_data = self.get_data(self.current.start)
        for i in range(len(d_data)//32):
            if not d_data[i*32]:
                d_data = d_data[:i*32] + data[:32] + d_data[(i+1)*32:]
                data = data[32:]
            if not data:
                break
        self.write_data(self.current.start, d_data)
        return data

    def clear_dir(self):
        d_data = self.get_data(self.current.start)
        zeroes, k = (b'\x00'*32, 0)
        for i in range(len(d_data)//32):
            i -= k
            if d_data[i*32] in [0xe5, 0x00]:
                k += 1
                d_data = d_data[:i*32] + d_data[(i+1)*32:] + zeroes
        self.write_data(self.current.start, d_data)

    def upwrite_data_by_cluster(self, n, data):
        if len(data) > self.len_clus:
            raise BigDataForCluster
        self.fo.seek(self.root_dir+(n-2)*self.len_clus)
        self.fo.write(data)

    def write_data(self, start, data):
        while start < 0x0ffffff8:
            self.upwrite_data_by_cluster(start, data[:self.len_clus])
            data = data[self.len_clus:]
            self.fo.seek(self.start_fat+start*4)
            start = self.read_num(4)

    def del_dir_record(self, start, length):
        data = list(self.get_data(self.current.start))
        for i in range(start, start+length):
            data[i*32] = 0xe5
        self.write_data(self.current.start, bytes(data))

    def read_num(self, n, num=None):
        result = 0
        data = num if num else self.fo.read(n)
        for i in range(n):
            result += data[i]*(256**i)
        return result

    def get_data(self, start):
        return b''.join(self.get_data_by_clusters(start))

    def parse_record(self, record):
        name = record[1:11]+record[14:26]+record[28:]
        for i in range(len(name)//2):
            if name[i*2:(i+1)*2] == b'\x00\x00':
                return name[:i*2]
        return name
