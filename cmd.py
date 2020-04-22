from reader import Reader, Type
from hexdump import HexDump
from argparse import ArgumentParser
from os import path, listdir, makedirs, lseek
from os.path import sep
import codecs

# {(Имя, описание): [(Имя аргумента, описание[, дефолт])*]}


commands =\
    {("cat", "Show text of file"):
        [("file", "file for reading"),
         ("encoding", "ecoding to read file, default = latin-1", "latin-1")],
     ("hd", "Show hexed file"): [("file", "file for reading")],
     ("cd", "Change directory"): [("dir", "destination, default = /", "/")],
     ("ls", "List file of directory (more data with ll)"):
        [("dir", "destination, default = .", ".")],
     ("export", "Exports files to host"):
        [("fr", "set file or dir in image, default = .", "."),
         ("to", "set dir or file at host, default = .", ".")],
     ("import", "Imports files from host"):
        [("fr", "set file or dir at host, default = .", "."),
         ("to", "set dir or file in image, default = .", ".")],
     ("load", "Open new image"): [("image", "name of new image")],
     ("rm", "Remove file/directory"): [("file", "file name")],
     ("md", "Make directory"): [("dir", "dir name")],
     ("cf", "Create empty file"): [("file", "file name")],
     ("fschk", "Check file system"): [],
     ("help", "Shows help information"): []}


class ArgparseWithExit(ArgumentParser):
    def exit(self, status=0, message=""):
        raise KeyboardInterrupt(message)


class NoSuchCommandError(Exception):
    def __str__(self):
        return "No such command"


class FileNotFoundError(OSError):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def __str__(self):
        return "{}: No such file or directory".format(self.fn)


class IsADirectoryError(OSError):
    def __init__(self, fn):
        super().__init__()
        self.name = fn

    def __str__(self):
        return "{}: is a directory".format(self.name)


class Cmd:
    def __init__(self, image_fn):
        self.reader = Reader(image_fn)
        self.dir = sep
        self.init_arg_pars()
        self.actions = {"load": self.load, "ls": self.ls, "cf": self.cf,
                        "import": self.import_file, "export": self.export_file,
                        "cd": self.cd, "md": self.md, "rm": self.rm,
                        "fschk": self.fschk, "cat": self.cat,
                        "hd": self.hd, "help": self.help}

    def init_arg_pars(self):
        self.parsers = {}
        for cmd in commands:
            kwargs = {"description": cmd[1], "prog": cmd[0]}
            self.parsers[cmd[0]] = ArgparseWithExit(**kwargs)
            for arg in commands[cmd]:
                kwargs = {"help": arg[1]}
                if len(arg) == 3:
                    kwargs["nargs"] = "?"
                    kwargs["default"] = arg[2]
                self.parsers[cmd[0]].add_argument(arg[0], **kwargs)
        self.parsers["ls"].add_argument('-l', action="store_true",
                                        help="use a long listing format")
        self.parsers["ls"].add_argument('-R', type=int, nargs='?', default=0,
                                        help="list subdirectories recursively")

    def execute(self, cmdl):
        name, *args = cmdl
        if name in self.actions:
            self.actions[name](self.parsers[name].parse_args(args))
        else:
            raise NoSuchCommandError

    def cd(self, p):
        d = self.dir
        directory = d.split(sep)[:-1]
        if not p.dir or p.dir[0] == sep:
            self.reader.cd(self.reader.root)
            directory = [""]
            if not p.dir:
                self.dir = sep
                return
        folders = p.dir.split(sep)
        for folder in folders:
            try:
                if folder not in [".", ""]:
                    if folder in "..":
                        directory.pop()
                    else:
                        directory.append(folder)
                    folder = self._find_file(folder)
                    self.reader.cd(folder)
            except Exception as e:
                self.dir = d
                self.cd(self.parsers["cd"].parse_args([d]))
                raise
        directory.append("")
        self.dir = sep.join(directory)

    def fschk(self, _):
        self._fake_cd(sep, self.reader.fschk)
        print("fs is ok")

    def cf(self, p):
        path = p.file.split(sep)
        self._fake_cd(sep.join(path[:-1]), self.reader.cf, path[-1])

    def md(self, p):
        path = p.dir.split(sep)
        self._fake_cd(sep.join(path[:-1]), self.reader.md, path[-1])

    def rm(self, p):
        path = p.file.split(sep)
        self._fake_cd(sep.join(path[:-1]), self._rm, path[-1])

    def load(self, p):
        self.reader, self.dir = (Reader(p.image), sep)

    def cat(self, p):
        path = p.file.split(sep)
        self._fake_cd(sep.join(path[:-1]), self._cat, p.encoding, path[-1])

    def ls(self, p):
        self._fake_cd(p.dir, self._ls, p.l, p.R)

    def help(self, _):
        for p in self.parsers:
            print(p)
            self.parsers[p].print_help()
            print("\n")

    def import_file(self, p):
        self._fake_cd(p.to, self._import, p.fr)

    def export_file(self, p):
        path = p.fr.split(sep)
        self._fake_cd(sep.join(path[:-1]), self._export, path[-1], p.to)

    def hd(self, p):
        path = p.file.split(sep)
        if len(path) == 1:
            self._hd(path[-1])
            return
        self._fake_cd(sep.join(path[:-1]), self._hd, path[-1])

    def add_action(self, name, func, descr):
        self.actions[name] = func
        self.parsers[name] = ArgparseWithExit(description=descr, prog=name)

# -------------------------------------------------------------------- #

    def _fake_cd(self, path, func, *args):
        dir_, p = (self.dir, self.parsers["cd"].parse_args([path]))
        try:
            if p.dir not in ".":
                self.cd(p)
            func(*args)
        finally:
            self.cd(self.parsers["cd"].parse_args([dir_]))

    def _rm(self, fn):
        if fn not in '..':
            self.reader.rm(self._find_file(fn))

    def _cat(self, encoding, fn):
        for data in self._get_data(fn):
            text = codecs.decode(data, encoding=encoding, errors='replace')
            text = map(
                lambda x: x if x.isprintable() or x.isspace() else '?', text)
            print(''.join(text), end='')

    def _import(self, fr):
        name = fr.split(sep)[-1]
        if path.isdir(fr):
            self.reader.md(name)
            self.reader.cd(self.reader.current)
            self.reader.cd(self._find_file(name))
            for f in listdir(fr):
                self._import(path.join(fr, f))
        else:
            self._import_file_data(fr, name)

    def _export(self, fr, to):
        try:
            self.cd(self.parsers["cd"].parse_args([fr]))
            dest = path.join(to, self.dir.split(sep)[-2])
            makedirs(dest, exist_ok=True)
            for f in self.reader.files:
                if f.name not in '..':
                    self._export(f.name, dest)
            if self.dir != sep:
                self.cd(self.parsers["cd"].parse_args([".."]))
        except Exception:
            fn = path.join(to, fr) if path.isdir(to) else to
            with open(fn, 'wb') as fo:
                for data in self._get_data(fr):
                    fo.write(data)

    def _hd(self, fn):
        n = 0
        for data in self._get_data(fn):
            for line in HexDump(data, 16, n).lines:
                print(line)
            n += len(data)

    def _rm(self, fn):
        self.reader.rm(self._find_file(fn))

    def _ls(self, use_long, depth_rec, par=[]):
        if depth_rec is None:
            depth_rec = -1
        for f in self.reader.files:
            fn = str(f)
            if fn in '..':
                continue
            fn = "{}/{}".format("/".join(par), fn) if par else fn
            print(f.get_line(fn) if use_long else fn)
            if depth_rec and f.type == Type.dir_:
                self.reader.cd(f)
                par.append(f.name)
                self._ls(use_long, depth_rec-1, par)
                par.pop()
                self.reader.cd(self.reader.files[1])

    def _find_file(self, name):
        for file_ in self.reader.files:
            if file_.name == name:
                return file_
        raise FileNotFoundError(name)

    def _import_file_data(self, dest_fn, fn):
        with open(dest_fn, 'rb') as f:
            size = lseek(f.fileno(), 0, 2)
            n = self.reader.add_cluster() if size else 0
            self.reader.cf(fn, n, size)
            self.reader.cd(self.reader.current)
            f.seek(0)
            data = f.read(self.reader.len_clus)
            while data:
                self.reader.upwrite_data_by_cluster(n, data)
                data = f.read(self.reader.len_clus)
                if data:
                    n = self.reader.add_cluster(n)

    def _get_data(self, fn):
        file_ = self._find_file(fn)
        if file_.type == Type.dir_:
            raise IsADirectoryError(path.join(self.dir, file_.name))
        size = file_.size
        for data in self.reader.get_data_by_clusters(file_.start):
            data = data[:size]
            size -= len(data)
            yield data
            if size <= 0:
                return
