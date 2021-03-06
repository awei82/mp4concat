# mp4concat
Python scripts to concatenate/merge/stitch together multiple MP4 and SRT video files.

`MP4concat.py` concatenates multiple MP4 files and adds chapter information to the merged file based on the original input file names.
The script calls the `ffmpeg` and `MP4Box` executables under the hood to do the concatenation and chapter file naming:  
- https://ffmpeg.org/  
- https://github.com/gpac/gpac/wiki/MP4Box-Introduction   

The `ffmpeg` and `MP4Box` executables are located in the `bin/` directory.

Note - `ffmpeg` will need to generate intermediate files as part of its concatenation process. The python script will need to be able to write temporary files to its current working directory.

Large portions of this project were based on https://github.com/sverrirs/mp4combine

`SRTconcat.py` concatenates SRT subtitle files together and aligns the input subtitle files with the final merged MP4 ouput.

## Build and activate the virtual environment
```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## MP4concat usage
```
mkdir output
python MP4concat.py -i input/*.mp4 -o output/merged_video.mp4
```

## SRTconcat usage
```
python SRTconcat.py -i input/*.srt -o output/merged_video.srt --mp4 output/merged_video.mp4
```

### Notes
- If you have trouble viewing the chapter information in your concatenated video, try using another video player such as [VLC](https://www.videolan.org/vlc/index.html).  
- This script is intended to be used with video files w/ identical video resolutions. If you need to merge files with different resolutions, try https://github.com/sverrirs/mp4combine
