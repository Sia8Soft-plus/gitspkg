import os
import argparse
# from gits import cmds
from gits.commands import cmds
from conf import config


def parse_args():
    parser = argparse.ArgumentParser(
        description='gits = gis = git + git submodule + conan/vcpkg. Version: {}. Publish date: {}'.format(
            config.VERSION, config.PUBLISH_DATE))
    parser.add_argument('command', type=str, help='port number to kill the process.')  # 命令
    parser.add_argument('argument', type=str, nargs='?', help='port number to kill the process.')  # 参数

    # flags
    parser.add_argument('-v', '--version', action='store_true', help='Show version.')

    parser.add_argument('-sip', '--set_lean_remote_ip', default='', help='Set lean remote IP.')
    parser.add_argument('-susr', '--set_lean_remote_user', default='', help='Set lean remote user.')
    parser.add_argument('-spwd', '--set_lean_remote_pwd', default='', help='Set lean remote password.')
    parser.add_argument('-srpath', '--set_lean_remote_path', default='', help='Set lean remote path.')
    parser.add_argument('-slpath', '--set_lean_local_path', default='', help='Set lean local path.')

    parser.add_argument('-ip', '--lean_remote_ip', action='store_true', help='Lean remote IP flag.')
    parser.add_argument('-usr', '--lean_remote_user', action='store_true', help='Lean remote user flag.')
    parser.add_argument('-pwd', '--lean_remote_pwd', action='store_true', help='Lean remote password flag.')
    parser.add_argument('-rpath', '--lean_remote_path', action='store_true', help='Lean remote path flag.')
    parser.add_argument('-lpath', '--lean_local_path', action='store_true', help='Lean local path flag.')

    parser.add_argument('-ln', '--lean', action='store_true', help='Lean flag.')
    parser.add_argument('-d', '--dep', action='store_true', help='Dependency flag.')
    parser.add_argument('-s', '--specific', default='', help='Specific option.')
    parser.add_argument('-lc', '--local',  action='store_true', help='Local option.')
    parser.add_argument('-r', '--remote',  action='store_true', help='Remote option.')
    parser.add_argument('--import', dest='import_check', action='store_true',
                        help='Check the import status of files declared in lean.manifest for a given path.')
    parser.add_argument('--recursive', action='store_true',
                        help='Recursively check all sub-dependencies in the given path.')
    parser.add_argument('--object', "--obj", action='store_true',
                        help='Recursively check all sub-dependencies in the given path.')
    parser.add_argument('--to', dest='to_destination', nargs='?', const=None,  default=None,
        help='Specify the destination path. If used without a path, a default action is taken.'
    )
    parser.add_argument(
        '-m', '--manifest',
        default=None,
        dest="manifest_filename",
        help="Specify the manifest file to use (default: lean.manifest)"  # 帮助信息
    )
    target_type_group = parser.add_mutually_exclusive_group()

    target_type_group.add_argument('--dll', action='store_true',
                                   help='Set the target as a shared library (SHARED).')
    target_type_group.add_argument('--lib', action='store_true',
                                   help='Set the target as a static library (STATIC).')
    target_type_group.add_argument('--exe', action='store_true',
                                   help='Set the target as the executable file (default).')
    parser.add_argument('--obj-name', dest='obj_name', nargs='+', const=None, default=None,
                        help='Specify the destination path. If used without a path, a default action is taken.'
                        )
    parser.add_argument('--spec',
                        nargs='+',
                        default=[],
                        help='Specify specific packages to update (e.g., --spec pkg1 pkg2==1.0)')
    parser.add_argument('--no-obj',
                        dest='no_obj',
                        action='store_true',  # 关键是这一行
                        help='如果指定此参数，后续将不执行 new-obj 等操作')

    parser.add_argument('--compiler', dest='compiler', default=None,
                        help='Designated compiler (e.g., VS2019)')
    args, remaining = parser.parse_known_args()

    return args, remaining


def main():
    args, remaining = parse_args()
    cmds(args, remaining)
    # print(args)


if __name__ == "__main__":
    main()
