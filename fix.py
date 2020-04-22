#!/usr/bin/env python3.6


from reader import Reader, get_bytes, Type, PermissionDenied
from os import path
from hexdump import HexDump
import argparse
import sys


class ErrorsFixed(Exception):
    def __init__(self, errors):
        self.errors = errors
        super().__init__()

    def __str__(self):
        if not self.errors:
            return "No errors found"
        self.errors.insert(0, "Fixed errors:")
        return "\n".join(self.errors)


class Fixer(Reader):
    def __init__(self, args):
        super().__init__(args.image)
        if not self.writable:
            raise PermissionDenied
        self.errors = []
        visited = [0, 1] + self.fix_self_crossing(self.root.start)
        visited = self.fix_crosses(visited)
        self.fo.seek(self.start_fat)
        losted = []
        for i in range(self.len_fat//4):
            if self.read_num(4) and i not in visited:
                losted.append(i)
        self.repair_losted(losted)
        self.fo.close()
        raise ErrorsFixed(self.errors)

    def fix_crosses(self, visited, is_root=True):
        files = self.files
        isnrt = len(files) < 2 or (files[0].name, files[1].name) != (".", "..")
        if not is_root:
            if isnrt:
                self.fix_dir_struct(self.current)
            files = files[2:]
        not_fixed = True
        while not_fixed:
            for f in files:
                clusters = self.check_crosses(visited, f)
                size = len(clusters) * self.len_clus
                visited += clusters
                if f.type == Type.dir_:
                    if f.size:
                        self.fix_size(f, 0)
                    self.ps = self.current.start
                    self.cd(f)
                    self.fix_crosses(visited, False)
                    self.cd(self.files[1])
                elif f.size not in range(size-self.len_clus, size+1):
                    self.fix_size(f, size)
            not_fixed = False
        return visited

    def check_crosses(self, visited, f):
        clusters = self.fix_self_crossing(f.start)
        for c in clusters:
            if c in visited:
                return self.copy_crossed(clusters, visited, f)
        return clusters

    def copy_crossed(self, clusters, visited, f):
        end = self.prepare_to_copy(clusters, visited, f)
        result = [end]
        self.errors.append("Crossed file")
        for c in clusters[1:]:
            if c in visited or f.type == Type.dir_:
                self.fo.seek(self.root_dir+(c-2)*self.len_clus)
                data = self.fo.read(self.len_clus)
                end = self.add_cluster(end)
                self.fo.seek(self.root_dir+(end-2)*self.len_clus)
                self.fo.write(data)
            else:
                end = c
            result.append(end)
        return result

    def prepare_to_copy(self, clusters, visited, f):
        self.del_dir_record(*f.blocks)
        self.cd(self.current)
        if f.type == Type.dir_:
            self.md(f.name)
            self.cd(self.current)
            end = self.files[-1].start
            if clusters[0] not in visited:
                self.fo.seek(self.start_fat+clusters[0]*4)
                self.write(b'\x00'*4)
            self.copy_clust(clusters[0], end)
        else:
            end = self.add_cluster() if clusters[0] in visited else clusters[0]
            self.cf(f.name, end, f.size)
            if clusters[0] in visited:
                self.copy_clust(clusters[0], end)
        return end

    def copy_clust(self, last, new):
        self.fo.seek(self.root_dir+(last-2)*self.len_clus)
        data = self.fo.read(self.len_clus)
        self.fo.seek(self.root_dir+(new-2)*self.len_clus)
        self.fo.write(data)

    def repair_losted(self, losted):
        if losted:
            self.errors.append("Found losted clusters")
            self.create_LOSTFOUND()
            for start, size in self.get_files(losted):
                name = self.get_losted_name()
                self.cf(name, start, size*self.len_clus)
                self.cd(self.current)

    def get_losted_name(self):
        n = 0
        f_names = list(map(lambda x: str(x), self.files))
        while True:
            name = "FILE.{}".format(n)
            if name not in f_names:
                return name
            n += 1

    def create_LOSTFOUND(self):
        self.cd(self.root)
        dir_ = "LOSTFOUND"
        self.md(dir_, False)
        self.cd(self.root)
        for f in self.files:
            if str(f) == dir_:
                self.cd(f)
                break

    def get_files(self, losted):
        files, len_ = [], len(losted)
        while losted:
            cs, n = 0, losted.pop(0)
            start = n
            while n < 0x0ffffff8 and n in losted:
                n = self.read_num(4)
                losted.remove(n)
            while cs != start:
                cs, to_rem = start, []
                for c in losted:
                    self.fo.seek(self.start_fat+c*4)
                    if self.read_num(4) == start:
                        start = c
                        to_rem.append(c)
                for c in to_rem:
                    losted.remove(c)
            files.append((start, len_-len(losted)))
            len_ = len(losted)
        return files

    def fix_self_crossing(self, start):
        err = []
        result = self.get_clusters(start, err)
        if err:
            self.errors.append("Self-crossed file")
            self.fo.seek(self.start_fat+result[-1]*4)
            self.fo.write(b'\xf8\xff\xff\x0f')
        return result

    def fix_size(self, f, size):
        self.errors.append("Illegal size")
        s = sum(f.blocks)
        data = self.get_data(self.current.start)
        rec = data[(s-1)*32: s*32][:-4] + get_bytes(size)
        data = data[:(s-1)*32] + rec + data[s*32:]
        self.write_data(self.current.start, data)

    def fix_dir_struct(self, d):
        self.errors.append("Wrong directory structure")
        data = self.get_data(d.start)
        zeroes = 0
        for i in range(len(data)//32):
            zeroed_rec = data[i*32:(i+1)*32] == b'\x00'*32
            if data[i*32:i*32+2] in b'.. ' or zeroed_rec:
                data = data[:i*32] + data[(i+1)*32:]
                zeroes += 32
        data = self.make_dos_record(b'.', Type.dir_, d.start, 0) +\
            self.make_dos_record(b'..', Type.dir_, self.ps, 0) +\
            data + b'\x00'*zeroes
        self.write_data(d.start, data)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('image', type=str, help="open image")
    try:
        fix = Fixer(parser.parse_args())
    except Exception as e:
        sys.exit(e)
    except KeyboardInterrupt:
        print()
