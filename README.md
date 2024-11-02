## Prerequisites

You must build on Linux or macOS.

The script can build the necessary compilers for HAL for your machine and Windows.

There are dependencies, build the compilers for your system: --build_mingw, --build_elf
Then build the compilers capable of running on Windows: --build_win_mingw
And finally: --build_win_elf

Use the pack equivalents to archive and distribute the compilers

To build the compilers for HAL you need:
- look at the extracted sopurces there is a file
- or inspect gcc documentation

To build OVMF.fd follow the steps in the EDK2 guide
