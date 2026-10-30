#!/usr/bin/env bash

export PATH="$(brew --prefix ffmpeg-full)/bin:$PATH"
export PROJECT_ROOT=$( cd "$(dirname "$0")/.." ; pwd -P )
cd "$PROJECT_ROOT"

. venv/bin/activate

reefframe
