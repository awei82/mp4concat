"""
Python script that generates the necessary ffmpeg/mp4box commands to concatinate multiple video files 
together and generates a chapter file that marks the beginning of each concatenated file in the final result.

Significant portions of this code were based on https://github.com/sverrirs/mp4combine

See: https://github.com/awei82/mp4concat
Author: Andrew Wei
"""

import colorama
import humanize # Display human readible values for sizes etc
import sys, os, time
from pathlib import Path # to check for file existence in the file system
import argparse # Command-line argument parser
import ntpath # Used to extract file name from path for all platforms http://stackoverflow.com/a/8384788
import glob # Used to do partial file path matching when listing file directories in search of files to concatinate http://stackoverflow.com/a/2225582/779521
import subprocess # To execute shell commands 
import re # To perform substring matching on the output of mp4box and other subprocesses
from datetime import timedelta # To store the parsed duration of files and calculate the accumulated duration
from random import shuffle # To be able to shuffle the list of files if the user requests it
import csv # To use for the cutpoint files they are CSV files
from termcolor import colored # For shorthand color printing to the console, https://pypi.python.org/pypi/termcolor


class Colors(object):
    # Lambdas as shorthands for printing various types of data
    # See https://pypi.python.org/pypi/termcolor for more info
    filename = lambda x: colored(x, 'cyan')
    error = lambda x: colored(x, 'red')
    toolpath = lambda x: colored(x, 'yellow')
    #color_sid = lambda x: colored(x, 'yellow')
    #color_description = lambda x: colored(x, 'white')
    fileout = lambda x: colored(x, 'green')
    success = lambda x: colored(x, 'green')
    #color_progress_remaining = lambda x: colored(x, 'white')
    #color_progress_percent = lambda x: colored(x, 'green')

# Provides natural string sorting (numbers inside strings are sorted in the correct order)
# http://stackoverflow.com/a/3033342/779521
def natural_key(string_):
    """See http://www.codinghorror.com/blog/archives/001018.html"""
    return [int(s) if s.isdigit() else s for s in re.split(r'(\d+)', string_)]

# Creates a nice format of a datetime.timedelta structure, including milliseconds
def formatTimedelta(time_delta):
  timecode_s = time_delta.seconds
  timecode_ms = int(time_delta.microseconds / 1000)
  return '{:02}:{:02}:{:02}.{:03}'.format(timecode_s // 3600, timecode_s % 3600 // 60, timecode_s % 60, timecode_ms)


def main():
    colorama.init() # Initialize the colorama library

    # Compile the regular expressions
    regex_mp4box_duration = re.compile(r"Computed Duration (?P<hrs>[0-9]{2}):(?P<min>[0-9]{2}):(?P<sec>[0-9]{2}).(?P<msec>[0-9]{3})", re.MULTILINE)

    # Construct the argument parser for the commandline
    args = parseArguments()

    # Get the mp4box exec
    mp4exec = args.mp4box
    if mp4exec == None:
        mp4exec = 'bin/MP4Box.exe' if os.name == 'nt' else 'bin/MP4Box'

    # Get ffmpeg exec
    ffmpegexec = args.ffmpeg
    if ffmpegexec == None:
        ffmpegexec = 'bin/ffmpeg.exe' if os.name == 'nt' else 'bin/ffmpeg'

    # Create the output file names both for the video file and the intermediate chapters file
    output_file = Path(args.output)  

    # If the output files exist then either error or overwrite
    if( output_file.exists() ):
        if( args.overwrite ):
            os.remove(str(output_file))
        else:
            print( "Output file '{0}' already exists. Use --overwrite switch to overwrite.".format(Colors.filename(output_file.name)))
            sys.exit(0)

    # get list of input files
    if args.input:
        input_files = args.input
    elif args.input_dir:
        input_files = [args.input_dir + '/' + filename for filename in os.listdir(args.input_dir)]

    if not args.nosort:
        input_files = sorted(input_files, key=natural_key)

    file_infos = []
    # Only process verified mp4 files
    for in_file in input_files:
        print("File: {0}".format(Colors.filename(in_file)))
        mp4_fileinfo = parseMp4boxMediaInfo(in_file, mp4exec, regex_mp4box_duration)
        if mp4_fileinfo == None:
            raise Exception(f"Invalid input file: {in_file}. Exiting.")
            sys.exit(-1)
        else:
            file_infos.append(mp4_fileinfo)


    # If nothing was found then don't continue, this can happen if no mp4 files are found or if only the joined file is found
    if( len(file_infos) <= 0 ):
        print( "No mp4 video files found matching '{0}' Exiting.".format(args.match))
        sys.exit(0)

    print("Found {0} files".format(len(file_infos)))

    # Now create the list of files to create
    video_files = []
    chapters = []
    cumulative_dur = timedelta(seconds=0)
    cumulative_size = 0
    # Collect the file info data and chapter points for all files
    for file_info in file_infos:
        file_name = Path(file_info['file']).name
        video_files.append(file_info['file'])
        file_info_dur = file_info['dur']

        chapters.append({"name": Path(file_info['file']).stem, "timecode": formatTimedelta(cumulative_dur)})
        cumulative_dur += file_info_dur # Count the cumulative duration
        cumulative_size += file_info['size'] 

    # Add the final chapter as the end for this segment
    chapters.append({"name": "End", "timecode":formatTimedelta(cumulative_dur)})

    # Chapters should be +1 more than files as we have an extra chapter ending at the very end of the file
    print("{0} chapters, {1} running time, {2} total size".format( len(chapters), formatTimedelta(cumulative_dur), humanize.naturalsize(cumulative_size, gnu=True)))
    print( "Output: {0}".format(Colors.fileout(str(output_file))))

    # combine video files first
    print(Colors.toolpath("Combining the video files (ffmpeg)"))
    combineVideoFiles(ffmpegexec, video_files, output_file)
    
    # Now include the chapter marks
    print(Colors.toolpath("Adding chapters to combined video file (mp4box)"))
    addChaptersToVideoFile(mp4exec, output_file, chapters)

    # Read the created file to learn its final filesize
    size_out_file_kb = os.path.getsize(str(output_file)) / 1024
    print( Colors.toolpath("Final size of video file is: {0}".format(humanize.naturalsize(size_out_file_kb * 1024))))

    colorama.deinit() #Deinitialize the colorama library


# Executes the mp4box app with the -info switch and 
# extracts the track length and file size from the output
def parseMp4boxMediaInfo(file_name, mp4box_path, regex_mp4box_duration):
  
    # Get the size of the file in bytes
    statinfo = os.stat(file_name)
    file_size = statinfo.st_size #Size in bytes of a plain file

    # Run the app and collect the output
    proc_cmd = [mp4box_path, "-info", "-std", file_name]
    ret = subprocess.run(proc_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

    # Ensure that the return code was ok before continuing
    if ret.returncode != 0:
        print("Command {0} returned non-zero exit status {1}.".format(proc_cmd, ret.returncode))
        print("File {0} will be skipped".format(file_name))
        return None
    #ret.check_returncode()

    # Computed Duration 00:23:06.040 - Indicated Duration 00:23:06.040
    match = regex_mp4box_duration.search( ret.stdout )
    hrs = int(match.group("hrs"))
    min = int(match.group("min"))
    sec = int(match.group("sec"))
    msec = int(match.group("msec"))

    duration = timedelta(days=0, hours=hrs, minutes=min, seconds=sec, milliseconds=msec )
    return {'file':file_name, 'size':file_size, 'dur':duration }


# use ffmpeg to combine the video files
def combineVideoFiles(ffmpegexec, video_files, output_file):
    # create file list for ffmpeg
    filenames_file = createFilenamesFile(video_files)

    # concat_string = '"concat:{}"'.format('|'.join(video_files))
    prog_args = [ffmpegexec, '-hide_banner', '-f', 'concat', '-safe', '0', '-i', filenames_file, '-c', 'copy', str(output_file), '-y']
    _runSubProcess(prog_args, path_to_wait_on=output_file)

    # Delete the file list
    if os.path.exists(str(filenames_file)):
        os.remove(str(filenames_file))

def createFilenamesFile(input_files):
    filenames_file = 'filenames.txt'
    with open(filenames_file, 'w') as fp:
        for input_file in input_files:
            fp.write(f"file '{input_file}'\n")
    return filenames_file


# Calls mp4box to create the concatenated video file and includes the chapter file as well
def addChaptersToVideoFile(mp4box_path, video_file, chapters):
    # Write the chapters file to txt file
    chapters_file = createChaptersFile(chapters)

    # Construct the args to mp4box
    prog_args = [mp4box_path, '-tmp', '.', '-chap', str(chapters_file), str(video_file)]

    # Run the command
    _runSubProcess(prog_args)

    # Delete the chapters file
    if os.path.exists(str(chapters_file)):
        os.remove(str(chapters_file))

# Saves a list of chapter information to a chapter file in the common chapter syntax
def createChaptersFile(chapters):
    chapters_file = 'chapters.txt'
    with open(chapters_file, 'w') as fp:
        for chapter_idx, chapter in enumerate(chapters, 1):
            fp.write("CHAPTER{0}={1}\n".format(chapter_idx, chapter['timecode']))
            fp.write("CHAPTER{0}NAME=\"{1}\"\n".format(chapter_idx, chapter['name']))
            chapter_idx += 1
    return chapters_file


# Runs a subprocess using the arguments passed and monitors its progress while printing out the latest
# log line to the console on a single line
def _runSubProcess(prog_args, path_to_wait_on=None):

    print( " ".join(prog_args))

    # Force a UTF8 environment for the subprocess so that files with non-ascii characters are read correctly
    # for this to work we must not use the universal line endings parameter
    my_env = os.environ
    my_env['PYTHONIOENCODING'] = 'utf-8'

    retcode = None

    # Run the app and collect the output
    ret = subprocess.Popen(prog_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, env=my_env)
    try:
        longest_line = 0
        trace_lines = []
        while True:
            try:
                #line = ret.stdout.readline().decode('utf-8')
                line = ret.stdout.readline()
                if not line:
                    break
                trace_lines.append(line)
                line = line.strip()[:80] # Limit the max length of the line, otherwise it will screw up our console window
                longest_line = max( longest_line, len(line))
                sys.stdout.write('\r '+line.ljust(longest_line))
                sys.stdout.flush()
            except UnicodeDecodeError:
                continue # Ignore all unicode errors, don't care!

        # Ensure that the return code was ok before continuing
        retcode = ret.wait()
    except KeyboardInterrupt:
        ret.terminate()
        raise

    if( retcode != 0 ): 
        print( "Error while executing {0}".format(prog_args[0]))
        print(" Full arguments:")
        print( " ".join(prog_args))
        print( "Full error")
        print("\n".join(trace_lines))
        raise ValueError("Error {1} while executing {0}".format(prog_args[0], retcode))

    # If we should wait on the creation of a particular file then do that now
    total_wait_sec = 0
    if not path_to_wait_on is None and not path_to_wait_on.is_dir():
        while not path_to_wait_on.exists() or total_wait_sec < 5:
            time.sleep(1)
            total_wait_sec += 1

        if not path_to_wait_on.exists() or not path_to_wait_on.is_file() :
            raise ValueError("Expecting file {0} to be created but it wasn't, something went wrong!".format(str(path_to_wait_on)))

    # Move the input to the beginning of the line again
    # subsequent output text will look nicer :)
    sys.stdout.write('\n Done!\n')
    return retcode


def parseArguments():
    parser = argparse.ArgumentParser()
    
    parser.add_argument("-o", "--output", type=str,
                        help="The path and filename of the concatenated output file. If multiple files then the script will append a number to the filename.")
    parser.add_argument("-i","--input", type=str,  nargs='+',
                        help="List of mp4 files to concatenate.")
    parser.add_argument("-d", "--input_dir", type=str,
                        help="As an alternative to --input, provide a directory path to where the input files are located.")                                     
    parser.add_argument("--mp4box", type=str, 
                        help="Path to the MP4Box executable")
    parser.add_argument("--ffmpeg", type=str, 
                        help="Path to the ffmpeg executable")
    parser.add_argument("--overwrite", action="store_true",
                        help="Existing files with the same name as the output will be silently overwritten.")
    parser.add_argument("--nosort", action="store_true",
                        help="Maintain ordering of files as inputted (no natural sorting of input files before concatenation).") 
    args = parser.parse_args()


    if (args.input and args.input_dir):
        print("Only one of --input or --input_dir may be entered as an argument. Exiting.")
        sys.exit(0)

    if not (args.output and (args.input or args.input_dir)):
        print("--input and --output arguments required. Use -h to see all options.")
        sys.exit(0)

    return args


if __name__ == '__main__':
    main()
    
