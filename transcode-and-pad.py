#!/usr/bin/env python3

import argparse
import re
import sys
import math
import ffmpegio
import os


def main():

    # keep track of input filename -> output filename
    filename_map = {}

    #
    # command line arguments
    #
    parser = argparse.ArgumentParser(
        description='Align (pad) and transcode raw-tracks files.')

    parser.add_argument('--tmp_dir', default='/tmp',
                        action='store', help='tmp directory')
    parser.add_argument('--output_dir', default='.',
                        action='store', help='output directory')
    parser.add_argument('--ffmpeg_global_args', default='-hide_banner -loglevel error -stats',
                        action='store', help='arguments prepended to all ffmpeg commands')

    parser.add_argument('--video_framerate', default='30',
                        action='store', help='output video framerate - default is 30')
    parser.add_argument('--video_bitrate', default='5000k',
                        action='store', help='output video target bitrate - default is 5000k which is 5mb/s')
    parser.add_argument('--video_min_resolution_dimension', type=int, default=0,
                        action='store', help='force output resolution to be at least this big on the shortest side (eg 720) - default is to use the first frame\'s resolution as the output resolution, but this can result in smaller than a smaller than expected resolution')

    parser.add_argument('--allow-any-filename-format', default=False,
                        action='store_true',
                        help='allow filenames that do not match the raw-tracks filename format')
    parser.add_argument('--combine-matching-video-and-audio', default=False,
                        action='store_true',
                        help='output video+audio mp4 for any matching cam-video and cam-audio tracks')

    parser.add_argument('input_filenames', nargs='+', help='files to process')

    args = parser.parse_args()

    #
    # sanity check filename format and that all start times in the provided
    # batch of files match. (unless we're allowing any filename format)
    #
    if (not args.allow_any_filename_format):
        start_time = None
        for input_filename in args.input_filenames:
            track_start_time, _, _ = parse_raw_tracks_filename(input_filename)
            if (start_time is None):
                start_time = track_start_time
            if (start_time != track_start_time):
                print(
                    f"ERROR: start times don't all match, eg {start_time} != {track_start_time}", file=sys.stderr)
                sys.exit(1)

    #
    # process each input file
    #

    for input_filename in args.input_filenames:
        # get start_time and audio/video type info
        metadata = ffmpegio.probe.full_details(input_filename)
        # print(f"{metadata}", file=sys.stderr)
        start_time = metadata['streams'][0]['start_time']
        codec_type = metadata['streams'][0]['codec_type']
        if (codec_type == 'video'):
            first_frame_width = metadata['streams'][0]['width']
            first_frame_height = metadata['streams'][0]['height']
            aspect_ratio = first_frame_width / first_frame_height

        base_name = os.path.basename(input_filename)

        # transcode and pad
        if codec_type == 'audio':
            output_file_name = f"{args.output_dir}/{base_name}.padded.aac"
            filename_map[input_filename] = output_file_name
            transcode_and_pad_audio(
                input_filename, output_file_name, start_time,
                args.ffmpeg_global_args)
        elif codec_type == 'video':
            output_file_name = f"{args.output_dir}/{base_name}.padded.mp4"
            filename_map[input_filename] = output_file_name
            transcode_and_pad_video(
                input_filename, output_file_name, start_time,
                args.tmp_dir, args.ffmpeg_global_args,
                args.video_framerate, args.video_bitrate,
                args.video_min_resolution_dimension,
                first_frame_width, first_frame_height, aspect_ratio)

    #
    # if --combine-matching-video-and-audio is set, combine any matching
    # cam-video and cam-audio tracks into a single mp4 file
    #

    if (args.combine_matching_video_and_audio):
        # build list of video/audio track pairs
        # { uuid: [(track_name, filename), ...]}
        uuids = {}
        for input_filename in args.input_filenames:
            start_time, uuid, track_name = parse_raw_tracks_filename(
                input_filename)
            if uuid in uuids:
                uuids[uuid].append((track_name, input_filename))
            else:
                uuids[uuid] = [(track_name, input_filename)]
        # process
        for uuid, item in uuids.items():
            audiol = [filename for (track_name, filename)
                      in item if track_name == 'cam-audio']
            videol = [filename for (track_name, filename)
                      in item if track_name == 'cam-video']
            if (len(audiol) == 1 and len(videol) == 1):
                audio_filename = filename_map[audiol[0]]
                video_filename = filename_map[videol[0]]
                print(
                    f"found matching video/audio pair {audio_filename} / {video_filename}",
                    file=sys.stderr)
                output_filename = f"{args.output_dir}/{start_time}-{uuid}-combined.mp4"
                combine_video_and_audio(
                    video_filename, audio_filename, output_filename, args.ffmpeg_global_args)
            # do some additional sanity checking and print out warnings, to help
            # users track whether they're getting what they expect
            elif len(audiol) == 1 and len(videol) == 0:
                print(
                    f"found only audio track for {audiol[0]}", file=sys.stderr)
            elif len(audiol) == 0 and len(videol) == 1:
                print(
                    f"found only video track for {videol[0]}", file=sys.stderr)
            elif len(audiol) > 1 or len(videol) > 1:
                print(
                    f"found more than one audio or video track {audiol} {videol}", file=sys.stderr)


def parse_raw_tracks_filename(filename):
    # example raw-track filename: 1703174279145-02ce3bcb-bf5b-423f-9699-63fca113a952-cam-audio-1703174279270.webm
    # this is:
    #  <startRecording timestamp in ms>-<36 character uuid>-<track name>-<approx track start time>.<extension>
    pattern = r'^(?:.+/)*(\d+)-(.{36})-(.*)-\d+\.(\w+)'
    match = re.match(pattern, filename)
    if (match is None):
        print(
            f"ERROR: filename {filename} does not match expected pattern", file=sys.stderr)
        sys.exit(1)
    start_time = int(match.group(1))
    uuid = match.group(2)
    track_name = match.group(3)
    extension = match.group(4)
    if (extension != 'webm'):
        print(
            f"ERROR: filename {filename} does not have webm extension", file=sys.stderr)
        sys.exit(1)
    return start_time, uuid, track_name


def transcode_and_pad_audio(input_file_name, output_file_name, start_time, ffmpeg_global_args):
    # ffmpeg quirk: aresample needs to come before adelay in the filter chain
    command = f'-y -i {input_file_name} -af "aresample=async=1,adelay={math.floor(start_time*1000)}:all=true" -b:a 256k -acodec aac {output_file_name}'
    print(f"running {ffmpeg_global_args} {command}", file=sys.stderr)
    ffmpegio.ffmpeg(f'{ffmpeg_global_args} {command}')


def transcode_and_pad_video(input_file_name, output_file_name, start_time, tmp_dir,
                            ffmpeg_global_args, video_framerate, video_bitrate,
                            video_min_resolution_dimension,
                            first_frame_width, first_frame_height, aspect_ratio):
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
    # todo: make our tmp file names unique so actions/script can be run in parallel
    # todo: sanity check to see that output_file_name ends in '.mp4'

    # use the first frame's resolution for the padding video and the transcoding, unless
    # the user has specified a minimum resolution dimension. (it's a good idea to
    # specify a minimum resolution dimension, because the first frame's resolution might
    # be smaller than expected, for example the first frame might be from a small
    # simulcast layer)
    if (video_min_resolution_dimension == 0):
        width = first_frame_width
        height = first_frame_height
    else:
        print(
            f'{first_frame_width}x{first_frame_height} -- {aspect_ratio}', file=sys.stderr)
        if (aspect_ratio > 1):
            height = video_min_resolution_dimension
            width = math.floor(height * aspect_ratio)
        else:
            width = video_min_resolution_dimension
            height = math.floor(width * aspect_ratio)

    padding_tmp_filename = f'{tmp_dir}/padding.ts'
    video_tmp_filename = f'{tmp_dir}/video.ts'

    command = f'-y -f lavfi -i "color=c=black:s={width}x{height}" -t {start_time} -r {video_framerate} -b:v {video_bitrate} -c:v libx264 {padding_tmp_filename}'
    print(f"running {ffmpeg_global_args} {command}", file=sys.stderr)
    ffmpegio.ffmpeg(f'{ffmpeg_global_args} {command}')

    command = f'-y -i {input_file_name} -r 30 -vf scale={width}:{height} -b:v 5000k -c:v libx264 {video_tmp_filename}'
    print(f"running {ffmpeg_global_args} {command}", file=sys.stderr)
    ffmpegio.ffmpeg(f'{ffmpeg_global_args} {command}')

    command = f'-y -i "concat:{padding_tmp_filename}|{video_tmp_filename}" -c copy {output_file_name}'
    print(f"running {ffmpeg_global_args} {command}", file=sys.stderr)
    ffmpegio.ffmpeg(f'{ffmpeg_global_args} {command}')


def combine_video_and_audio(video_filename, audio_filename, output_filename, ffmpeg_global_args):
    command = f'-y -i {video_filename} -i {audio_filename} -c:v copy -c:a copy {output_filename}'
    print(f"running {ffmpeg_global_args} {command}", file=sys.stderr)
    ffmpegio.ffmpeg(f'{ffmpeg_global_args} {command}')


if __name__ == "__main__":
    main()  # The 'main' function is called here.
