
# raw-tracks processing

Daily's `raw-tracks` recording type saves video and audio streams
from a WebRTC session in individual files. The streams are recorded
without any transcoding or processing.

To work with these streams, it's usually necessary to:
  - transcode them,
  - fill gaps by duplicating video frames and resampling audio,
  - and package them into a container file format that editing tools can work with.

## transcode-and-pad.py

Takes a list of files and:
  - pads the beginning with silence (for audio) or black frames (for video) so that different streams from the same session can easily be time aligned
  - transcodes to aac (for audio) or mp4 (for video), filling gaps while doing so,
  - optionally combine any matching pairs of cam-video and cam-audio streams from the same client into a single mp4 file

### example usage:

```
# for each of the .webm files in the current directory, generate an
# aac or mp4 file that is ready to import into an editing program
# or use in an ffmpeg or GStreamer command

~/bin/transcode-and-pad.py *.webm
```

```
# take the two input files given as arguments, generate an aac file
# for the audio stream, an mp4 file for the video stream, and a 
# combined file that includes both tracks. store all three output
# files in a directory named `processed` 

~/bin/transcode-and-pad.py --output_dir ./processed --combine-matching-video-and-audio 1703174279145-02ce3bcb-bf5b-423f-9699-63fca113a952-cam-audio-1703174279270.webm 1703174279145-02ce3bcb-bf5b-423f-9699-63fca113a952-cam-video-1703174279271.webm
```

### installation

You will need the [Python `ffmpegio` module](https://pypi.org/project/ffmpegio/).

```
pip install ffmpegio
```

### notes

Most video processing programs/libraries don't handle timestamps correctly. In a perfect world, all programs would understand that a base timestamp isn't necessarily 0 and that there might be gaps between frames in a stream.

`raw-tracks` files all have timestamps relative to the starting time of the recording session they were produced by. For example, a track might have a first packet with a timestamp of 60.000 if the track started 60 seconds after the recording session started.

`raw-tracks` files also can have large gaps between frames. For example, when a mic is muted, no audio frames are written out to the `raw-tracks` stream.

`transcode-and-pad.py` fixes both these issues. All output files have a base timestamp of 0. To accomplish this without throwing away the relative timing information between tracks, files are padded at the beginning with audio silence or black video frames. Output streams are also encoded so that there are no gaps. (Audio streams are resampled to maintain a constant sample rate. Frames are duplicated as necessary in video streams to maintain a constant frame rate.)

The `transcode-and-pad.py` program expects input filenames to follow the standard `raw-tracks` format:

```
    <startRecording timestamp in ms>-<36 character uuid>-<track name>-<approx track start time>.webm
```

If you have files with non-standard filenames you can override the filename sanity checks by specifying the `--allow-any-filename-format` argument. Note that with non-standard filenames you won't be able to do the `--combine-matching-video-and-audio` operation.

