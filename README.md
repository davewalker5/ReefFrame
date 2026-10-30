[![GitHub issues](https://img.shields.io/github/issues/davewalker5/ReefFrame)](https://github.com/davewalker5/ReefFrame/issues)
[![Releases](https://img.shields.io/github/v/release/davewalker5/ReefFrame.svg?include_prereleases)](https://github.com/davewalker5/ReefFrame/releases)
[![License](https://img.shields.io/badge/License-mit-blue.svg)](https://github.com/davewalker5/ReefFrame/blob/main/LICENSE)
[![Language](https://img.shields.io/badge/language-python-blue.svg)](https://www.python.org)
[![GitHub code size in bytes](https://img.shields.io/github/languages/code-size/davewalker5/ReefFrame)](https://github.com/davewalker5/ReefFrame/)

# Overview

ReefFrame is a Python desktop application for preparing, enhancing and processing underwater action-camera footage using [FFmpeg](https://ffmpeg.org/).

## Background

ReefFrame grew out of a collection of Bash scripts developed to process GoPro footage recorded while snorkelling in the Maldives. Underwater filming presents some particular challenges: reduced contrast, muted colours, suspended particles, changing light conditions and camera movement can all affect the quality of the resulting footage.

The original scripts were developed to address some of these problems, as well as to handle more routine tasks such as format conversion, file-size reduction and extracting still images from video.

As the collection of scripts grew, so did the need for a more convenient and consistent way to use them. ReefFrame brings these operations together in a graphical desktop application, with configurable processing parameters, reusable presets and support for processing individual files or entire folders.

Although developed around GoPro snorkelling footage, ReefFrame is not tied to any particular camera and may be useful for other underwater video recordings.

## What ReefFrame Does

ReefFrame provides a graphical interface for several common video-processing operations:

- **Format conversion** — Convert MOV recordings to MP4
- **Dehazing** — Adjust contrast and brightness to improve the appearance of underwater footage
- **Video enhancement** — Apply a combined sequence of contrast, brightness and vibrance adjustments
- **Stabilisation** — Reduce unwanted camera movement using FFmpeg's two-pass video stabilisation filters
- **Video compression** — Reduce MP4 file sizes for more convenient storage and distribution
- **Still image extraction** — Capture individual frames from video recordings as PNG images
- **Animated GIF creation** — Convert short video clips into animated GIFs

Processing parameters can be adjusted through individual operation dialogs and saved as JSON presets for reuse. Operations can be applied to individual recordings or batches of files, with progress reporting and error handling.

The application uses FFmpeg as its processing engine, including the additional stabilisation capabilities provided by builds incorporating `libvidstab`.

## What ReefFrame Doesn't Do

ReefFrame is **not intended to be a general-purpose video editor**. It does not provide a timeline, clip sequencing, transitions, audio editing or the other facilities normally associated with a full video-editing application.

Nor does it attempt to perform sophisticated underwater image restoration. Its dehazing and enhancement operations use conventional image adjustments rather than algorithms that physically model and reverse the effects of light absorption and scattering underwater. They can improve the appearance of footage, but cannot recover detail that was never captured.

Similarly, stabilisation can reduce unwanted movement, but cannot eliminate every camera shake or compensate for severe motion blur.

ReefFrame does not include facilities for publishing videos to social media or other online services. It concentrates on **preparing and improving footage**, leaving subsequent editing, presentation and publication to other tools.

## Philosophy

ReefFrame is deliberately focused on doing a relatively small number of useful things well.

It provides a convenient, repeatable way to process underwater recordings without requiring users to construct FFmpeg commands themselves, while retaining control over the processing parameters.

Its origins are quite practical: helping to make the most of footage from some memorable encounters beneath the surface of the Indian Ocean.

## Getting Started

Please see the [Wiki](https://github.com/davewalker5/ReefFrame/wiki) for the user guide, controls and further details.

## Authors

- **Dave Walker** - _Initial work_

## Feedback

To report an issue or suggest an improvement, please use the project's [GitHub Issues](https://github.com/davewalker5/ReefFrame/issues) page.

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
