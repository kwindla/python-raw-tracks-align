#!/usr/bin/env python3

import sys
import math
import ffmpegio


def main():
    input_file_name = sys.argv[1]
    metadata = ffmpegio.probe.full_details(input_file_name)
    # print(f"{metadata}", file=sys.stderr)
    start_time = metadata['streams'][0]['start_time']
    codec_type = metadata['streams'][0]['codec_type']

    if codec_type == 'audio':
        output_file_name = f"{input_file_name}.padded.aac"
        transcode_and_pad_audio(input_file_name, output_file_name, start_time)
    elif codec_type == 'video':
        output_file_name = f"{input_file_name}.padded.mp4"
        transcode_and_pad_video(input_file_name, output_file_name, start_time)


def transcode_and_pad_audio(input_file_name, output_file_name, start_time):
    # ffmpeg quirk: aresample needs to come before adelay in the filter chain
    command = f'-y -i {input_file_name} -af "aresample=async=1,adelay={math.floor(start_time*1000)}:all=true" -acodec aac {output_file_name}'
    print(f"running {command}", file=sys.stderr)
    ffmpegio.ffmpeg(command)


def transcode_and_pad_video(input_file_name, output_file_name, start_time):
    # we need to pad the beginning of the video file. the most robust way to
    # do this is to generate a file of padding, then concatenate the padding
    # video and our output video. ffmpeg has several options for concatenation.
    # we want to use file-level concatenation, so that we can encode our output
    # video once. file-level concatenation requires two videos with the same
    # codec, resolution, and frame rate in a container that's friendly to
    # this file-level concatenation operation.
    # let's do the following
    #  1. generate an mp4 file of padding, in a .ts container
    #  2. generate an mp4 file of the video, in a .ts container
    #  3. concatenate the two files, copying the video stream into an mp4 container
    # todo: make our tmp file names opaque so this script can be run in parallel
    # todo: check to see that output_file_name ends in '.mp4'
    command = f'-y -f lavfi -i "color=c=black:s=1280x720" -t {start_time} -r 30 -b:v 5000k -c:v libx264 /tmp/padding.ts'
    ffmpegio.ffmpeg(command)
    # todo: make the '-vf scale=1280:720' configurable
    command = f'-y -i {input_file_name} -r 30 -vf scale=1280:720 -b:v 5000k -c:v libx264 /tmp/video.ts'
    ffmpegio.ffmpeg(command)
    command = f'-i "concat:/tmp/padding.ts|/tmp/video.ts" -c copy {output_file_name}'
    ffmpegio.ffmpeg(command)


if __name__ == "__main__":
    main()  # The 'main' function is called here.
