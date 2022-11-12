#!/usr/bin/env python
# author: Bob Whelton <robert@whelton.net>

from collections import defaultdict
from os import getcwd, walk, mkdir, makedirs
from os.path import join, exists, getmtime, relpath, islink
from shutil import copystat, copy2
from time import ctime, sleep
import argparse
from json import dumps, load, dump


REPORT_NAME = 'duplication-report'
UNREADABLE_REPORT_NAME = 'unreadable-files-report'
TARGET_DIR = 'DEDUPLICATED'


def verify():
    print("As I said, I am not sure I can do this yet...")
    sleep(2)
    print("Nope.")


def print_report(clargs, report_name: str):
    if exists(report_name):
        with open(report_name) as report_file:
            found_files = load(report_file)
        if clargs.counts:
            counts = []
            for file, entries in found_files.items():
                entries.sort(key=lambda x: x['last_modified'])
                counts.append((len(entries), file, entries[-1]['directory']))
            print(f"count  filename, director last found in")
            print(f"------+--------------------------------------------------------------------------")
            counts.sort(key=lambda x: x[0])
            for count, file, directory in counts:
                print(f"{count:>5} | {file}")
                print(f"      | {directory}")
        elif clargs.json:
            for file, entries in found_files.items():
                for record in entries:
                    record['last_modified'] = ctime(record['last_modified'])
            print(dumps(found_files, indent=2, sort_keys=True))
        else:
            print("filename,modified timestamp,director,modified timestamp,directory,...")
            for file, entries in sorted(found_files.items()):
                file = file.replace('"', "'")
                print(f'"{file}"', end=',')
                entries.sort(key=lambda x: x['last_modified'], reverse=True)
                for info in entries:
                    directory = info["directory"].replace('"', "'")
                    print(ctime(info["last_modified"]), end=',')
                    print(f'"{directory}"', end=',')
                print(end='\n')
    else:
        print(f"no report by the name of '{report_name}' was found in the current directory '{getcwd()}'")


def generate_report(directories: list):
    found_files = defaultdict(list)
    for search_dir in directories:
        print(f"searching all files in {search_dir}")
        for path, dirs, files in walk(search_dir):
            for f in files:
                if not (f.startswith('.') or islink(join(path, f))):
                    record = {'directory': relpath(path)}
                    try:
                        record['last_modified'] = getmtime(join(path, f))
                    except FileNotFoundError:
                        record['last_modified'] = 0.0
                        record['file not found'] = True
                    found_files[f].append(record)
    report_name = REPORT_NAME
    tries = 0
    while exists(f"{report_name}.txt") and tries < 1000:
        tries += 1
        if '_' in report_name:
            name, number = report_name.split('_')
            number = int(number) + 1
            report_name = f"{name}_{number}"
        else:
            report_name = f"{report_name}_1"
    if tries < 1000:
        with open(f'{report_name}.txt', 'w') as report_file:
            dump(found_files, report_file, indent=2)
        print(f"I have written the report to '{join(getcwd(), f'{report_name}.txt')}'. Goodbye.")
    else:
        print(f"Unable to create a uniquely named report. Please delete files with names like '{report_name}'")


def deduplicate(destination_specs: list, report_name: str):
    """
    Examples of dest_strings:
        NewAccount1:Joe
        NewAccount2:Bob,Mary,Eucharia
    :param destination_specs:
    :return:
    """
    if destination_specs:
        destinations = {}
        for arg in destination_specs:
            dest, accounts = arg.split(':')
            makedirs(join(TARGET_DIR, dest), exist_ok=True)
            for account in accounts.split(','):
                destinations[account] = dest
        if exists(report_name):
            with open(f"{UNREADABLE_REPORT_NAME}.txt", 'w') as unreadable:
                with open(report_name) as report_file:
                    found_files = load(report_file)
                count = 0
                total = len(found_files)
                last_percent = 0
                print(f"deduplicating {total} files...")
                for file, entries in found_files.items():
                    count += 1
                    percent = int(count / total * 100)
                    if percent > last_percent:
                        print(f"{percent:>3}% completed")
                        last_percent = percent
                    data = defaultdict(lambda: defaultdict(list))
                    for record in entries:
                        if '/' in record['directory']:
                            account, directory = record['directory'].split('/', maxsplit=1)
                            dest = destinations[account]
                            data[dest][directory].append(
                                {'account': account, 'last_modified': record['last_modified']})
                    for dest, directories in data.items():
                        for directory, items in directories.items():
                            items.sort(key=lambda x: x['last_modified'])
                            info = items[-1]
                            path = ''
                            for d in directory.split('/'):
                                path = join(path, d)
                                try:
                                    mkdir(join(TARGET_DIR, dest, path))
                                    copystat(join(info['account'], path), join(TARGET_DIR, dest, path))
                                except FileExistsError:
                                    pass
                            src = join(info['account'], directory, file)
                            dst = join(TARGET_DIR, dest, directory, file)
                            try:
                                copy2(src, dst, follow_symlinks=False)
                            except PermissionError as e:
                                print(f"{e}, src='{src}', dst='{dst}'", file=unreadable, flush=True)
        else:
            print(f"no report by the name of '{report_name}' was found in the current directory '{getcwd()}'")
    else:
        print("Please specify some destination specifications")


def main(clargs):
    if clargs.verify:
        verify()
    elif clargs.report:
        print_report(clargs, clargs.report)
    elif clargs.deduplicate:
        deduplicate(clargs.directories, clargs.report)
    else:
        if clargs.directories:
            generate_report(clargs.directories)
        else:
            print("I have nothing to do here, please list some directories for me to search.")


def get_clargs():
    parser = argparse.ArgumentParser(
        description="Identifies duplicate files by name and generates a report of locations where each"
                    " file exists in duplicate. This includes the timestamp of the last modification time"
                    " in each location. By default, with no optional arguments, this will only produce a report"
                    " on the duplicate files found in the given directories."
    )
    parser.add_argument(
        "-r", "--report",
        help="Read data from the report with the given filename and either print it or deduplicate (with -DD option)."
    )
    parser.add_argument(
        "-c", "--counts", action="store_true", default=False,
        help="Only show the count of duplicates per filename rather than the list of all duplicates."
             " Works only with the --report option."
    )
    parser.add_argument(
        "-j", "--json", action="store_true", default=False,
        help="Print the report in JSON format. Otherwise it is printed in CSV."
    )
    parser.add_argument(
        "-DD", "--deduplicate", action="store_true", default=False,
        help="Execute the deduplification routine, which will copy the most recently modified version to"
             " a new directory."
    )
    parser.add_argument(
        "-f", "--find", action="store_true", default=False,
        help="Look up the given file in the report that is produced by default, displaying the locations and"
             " last modification date-times."
    )
    parser.add_argument(
        "-v", "--verify", action="store_true", default=False,
        help="I am not sure I can do this yet."
    )
    parser.add_argument(
        "directories", nargs="*",
        help="List the base directories in which to search."
    )
    return parser.parse_args()


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    main(get_clargs())
