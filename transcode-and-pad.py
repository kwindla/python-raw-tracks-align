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
    # command = f'-y -f lavfi -i color=c=black:s=1280x720:r=30:d={math.floor(start_time*1000)} -i {input_file_name} -filter_complex "[0:v][1:v]concat=n=2:v=1:a=0[outv]" -map "[outv]" {output_file_name}'
    # ffmpeg has several options for concatenation. but they all have
    # limitations. here again our files that are almost nearly raw video
    # frames from the rtp stream cause issues for ffmpeg. the most robust
    # way forward is to generate an mpeg2 file to pad the beginning of
    # the video, to transcode the rtp video stream to mpeg2, then to use
    # ffmpeg's concat demuxer to concatenate the two files.
    command = f'-y -f lavfi -i "color=c=black:s=1280x720" -t {start_time} -r 30 -b:v 24000 /tmp/tmp-padding.mpg'
    ffmpegio.ffmpeg(command)
    command = f'-y -i {input_file_name} -r 30 -b:v 24000 /tmp/tmp-video.mpg'
    ffmpegio.ffmpeg(command)
    ffconcat = ffmpegio.FFConcat()
    ffconcat.add_file("/tmp/tmp-padding.mpg")
    ffconcat.add_file("/tmp/tmp-video.mpg")
    with ffconcat:
        ffmpegio.transcode(ffconcat, '/tmp/tmp-concatenated.mpg',
                           f_in='concat', codec='copy', safe_in=0, overwrite=True)
    command = f'-y -i /tmp/tmp-concatenated.mpg -c:v libx264 -preset slow -crf 10 {output_file_name}'
    ffmpegio.ffmpeg(command)


if __name__ == "__main__":
    main()  # The 'main' function is called here.
