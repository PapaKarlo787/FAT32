#!/usr/bin/env python3.6


from cmd import Cmd
import shlex
import argparse
import re
import sys
import readline


class Fat:
    def __init__(self, args):
        self.is_act = True
        self.cons = Cmd(args.image)
        self.cons.add_action("exit", self.exit, "Exit from viwer")
        if args.cmd:
            self.execute(args.cmd)
            sys.exit(0)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.cons.reader.fo.close()

    def main(self):
        while self.is_act:
            try:
                self.execute(shlex.split(input("{} # ".format(self.cons.dir))))
            except EOFError:
                print()

    def execute(self, cmdl):
        try:
            if cmdl:
                self.cons.execute(cmdl)
        except Exception as e:
            print("{}: {}".format(cmdl[0], e))
        except KeyboardInterrupt:
            pass

    def exit(self, *_):
        self.is_act = False


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('image', type=str, help="open image")
    parser.add_argument('cmd', type=str, nargs=argparse.REMAINDER,
                        help='cmd for exec')
    try:
        with Fat(parser.parse_args()) as fat:
            fat.main()
    except Exception as e:
        sys.exit(e)
    except KeyboardInterrupt:
        print()
