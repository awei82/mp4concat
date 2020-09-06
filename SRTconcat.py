"""
Python script that stitches together multiple srt files to generate subtitles for a concatenated video file

See: https://github.com/awei82/mp4concat
Author: Andrew Wei
"""

import argparse
from typing import NamedTuple
from datetime import datetime
import subprocess
import re
import os


# Provides natural string sorting (numbers inside strings are sorted in the correct order)
# http://stackoverflow.com/a/3033342/779521
def natural_key(string_):
    """See http://www.codinghorror.com/blog/archives/001018.html"""
    return [int(s) if s.isdigit() else s for s in re.split(r'(\d+)', string_)]


class Subtitle_Line(NamedTuple):
    start: datetime
    end: datetime
    text: str


def srt_file_to_subtitles(srt_file):
    with open(srt_file, 'r') as fp:
        srt = fp.read()

    srt_split = srt.split('\n')

    start_times = [x.split()[0] for x in srt_split[1::4]]
    start_times = [datetime.strptime(x, '%H:%M:%S,%f') for x in start_times]

    end_times = [x.split()[2] for x in srt_split[1::4]]
    end_times = [datetime.strptime(x, '%H:%M:%S,%f') for x in end_times]

    text_lines = srt_split[2::4]

    subtitles = [Subtitle_Line(*x) for x in zip(start_times, end_times, text_lines)]
    return subtitles


def align_subtitle_times(subtitles, start_time = None):
    '''
    Aligns subtitle timestamps to a start time.
    '''
    zero = datetime.strptime("00:00", "%H:%M")
    if start_time:
        new_start_times = [start_time + (line.start - zero) for line in subtitles]
        new_end_times = [start_time + (line.end - zero) for line in subtitles]
        new_subtitles = [Subtitle_Line(*x) for x in zip(new_start_times, new_end_times, [line.text for line in subtitles])]
        return new_subtitles
    else:
        return subtitles


def write_subtitles_to_file(subtitles, output_file):
    with open(output_file, 'w') as fp:
        for n, line in enumerate(subtitles, 1):
            fp.write(str(n) + '\n')
            fp.write(f"{line.start.strftime('%H:%M:%S,%f')[:-3]} --> {line.end.strftime('%H:%M:%S,%f')[:-3]}\n")
            fp.write(line.text + '\n')
            fp.write('\n')
            

def get_alignment_start_times(mp4_file, mp4Box_exe = '../bin/MP4Box'):
    '''
    Captures chapter timestamps from mp4 file
    to be used for aligning subtitle times
    '''
    result = subprocess.run([mp4Box_exe, '-dump-chap-ogg', mp4_file, '-out', '/dev/stdout'], 
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    result_str = result.stdout.decode('utf-8')

    if result.returncode != 0:
        raise Exception(f'{mp4Box_exe} failed to read chapter data from "{mp4_file}". Exiting')
    elif result.stderr.decode('utf-8').strip() == 'No chapters or chapters track found in file':
        raise Exception(f'No chapters or chapters track found in file "{mp4_file}". Exiting')

    chapters = result_str.split('\n')[::2][:-1]
    timestamps_str = [x.split('=')[1] for x in chapters]
    timestamps = [datetime.strptime(x, '%H:%M:%S.%f') for x in timestamps_str]
    return timestamps

def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("-i","--input", type=str, nargs='+',
                        help="List of srt files to concatenate.")
    parser.add_argument("-d", "--input_dir", type=str,
                        help="As an alternative to --input, provide a directory path to where the input files are located.")   
    parser.add_argument("-o", "--output", type=str, 
                        help="Location to output concatenated srt file.")
    parser.add_argument("-m", "--mp4", type=str,
                        help="(Optional) MP4 file w/ chapter timestamps aligned to the input files.")
    parser.add_argument("--nosort", action="store_true",
                        help="Maintain ordering of files at inputted (no natural sorting of input files before concatenation).")
    args = parser.parse_args()

    if (args.input and args.input_dir):
        print("Only one of --input or --input_dir may be entered as an argument. Exiting.")
        exit()

    if not (args.output and (args.input or args.input_dir)):
        print("--input and --output arguments required. Use -h to see all options.")
        exit()

    return args


def main():
    args = parse_arguments()

    # get list of input files
    if args.input:
        input_files = args.input
    elif args.input_dir:
        input_files = [args.input_dir + '/' + filename for filename in os.listdir(args.input_dir)]

    if not args.nosort:
        input_files = sorted(input_files, key=natural_key)


    srt_files = input_files
    print('srt files:')
    for srt_file in srt_files:
        print(f' - {srt_file}')


    # use mp4 chapter offsets to align subtitles
    if args.mp4:
        start_times = get_alignment_start_times(args.mp4)
        if len(start_times) < len(args.input):
            raise Exception('Error: # of chapters in MP4 file does not match # of input srt files. Exiting')
            exit(-1)
    else:
        start_times = [None]


    merged_subtitles = []
    for i, srt_file in enumerate(srt_files):
        subtitles = srt_file_to_subtitles(srt_file)
        subtitles = align_subtitle_times(subtitles, start_times[i])

        if args.mp4:
            pass
        else:
            start_times.append(subtitles[-1].end)

        merged_subtitles += subtitles


    print(f'Writing merged subtitles to {args.output}')
    write_subtitles_to_file(merged_subtitles, args.output)

    
if __name__ == '__main__':
    main()
    