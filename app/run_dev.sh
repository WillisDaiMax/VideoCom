#!/bin/bash
# 开发时直接运行（不打包），界面调用 ../core
cd "$(dirname "$0")"
VIDEOCOM_CORE="$(cd ../core && pwd)" swift run
