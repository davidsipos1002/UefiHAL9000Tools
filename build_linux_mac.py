import os
import sys
import argparse
import time
import urllib.request
from tarfile import TarFile
import warnings
import glob
import subprocess
import shutil
import json
import platform
import lzma

def reporthook(count, block_size, total_size):
    global start_time
    if count == 0:
        start_time = time.time()
        return
    duration = time.time() - start_time
    progress_size = int(count * block_size)
    speed = int(progress_size / (1024 * duration))
    percent = int(count * block_size * 100 / total_size)
    sys.stdout.write('\r   %d%%, %d MB, %d KB/s, %d seconds passed' %
                    (percent, progress_size / (1024 * 1024), speed, duration))
    sys.stdout.flush()

def download_sources(binutils_version, gdb_version, gcc_version, mingw_version):
    binutils_link = 'https://ftp.gnu.org/gnu/binutils'
    binutils = f'binutils-{binutils_version}'
    binutils_filename = f'{binutils}.tar.gz'
    
    gdb_link = 'https://ftp.gnu.org/gnu/gdb'
    gdb = f'gdb-{gdb_version}'
    gdb_filename = f'{gdb}.tar.gz'

    gcc_link = 'https://ftp.gnu.org/gnu/gcc'
    gcc = f'gcc-{gcc_version}'
    gcc_filename = f'{gcc}.tar.gz'

    mingw_link = 'https://downloads.sourceforge.net/project/mingw-w64/mingw-w64/mingw-w64-release'
    mingw = f'mingw-w64-v{mingw_version}'
    mingw_filename = f'{mingw}.tar.bz2'

    os.makedirs('tarballs', exist_ok=True)

    print('   Downloading binutils...')
    urllib.request.urlretrieve(f'{binutils_link}/{binutils_filename}', f'tarballs/{binutils_filename}', reporthook)
    print()
    print('   Downloading gdb...')
    urllib.request.urlretrieve(f'{gdb_link}/{gdb_filename}', f'tarballs/{gdb_filename}', reporthook)
    print()
    print('   Downloading gcc...')
    urllib.request.urlretrieve(f'{gcc_link}/{gcc}/{gcc_filename}', f'tarballs/{gcc_filename}', reporthook)
    print()
    print('   Downloading mingw...')
    urllib.request.urlretrieve(f'{mingw_link}/{mingw_filename}', f'tarballs/{mingw_filename}', reporthook)
    print()

def extract_sources():
    os.makedirs('sources', exist_ok=True)
    for filename in os.listdir('tarballs'):
        if '.tar.' not in filename:
            continue
        print(f'   Extracting {filename}...')
        tar_file = TarFile.open(f'tarballs/{filename}', 'r')
        tar_file.extractall('sources')

def get_build_env(prefix, mingw_gcc, elf_gcc, target):
    env = os.environ.copy()
    env['PREFIX'] = prefix
    env['TARGET'] = target
    if elf_gcc:
        env['PATH'] = f'{os.path.abspath(elf_gcc)}/bin:{env['PATH']}' 
    if mingw_gcc:
        env['PATH'] = f'{os.path.abspath(mingw_gcc)}/bin:{env['PATH']}' 
    env['PATH'] = f'{os.path.abspath(prefix)}/bin:{env['PATH']}' 
    return env

def get_subprocess_output(pipe):
    while pipe.poll() is None:
        l = pipe.stdout.readline()
        print(l.decode('utf-8'), end='')
    print(pipe.stdout.read().decode('utf-8'), end='')

def build_mingw_toolchain(prefix):
    target = 'x86_64-w64-mingw32'
    env = get_build_env(prefix, '', '', target)

    os.makedirs(f'build/build-binutils-{target}', exist_ok=True)
    os.makedirs(f'build/build-gcc-{target}', exist_ok=True)
    os.makedirs(f'build/build-mingw-headers-{target}', exist_ok=True)
    os.makedirs(f'build/build-mingw-libs-{target}', exist_ok=True)
    os.makedirs(f'build/build-mingw-winpthreads-{target}', exist_ok=True)

    binutils = glob.glob('sources/*binutils*')[0]
    gcc = glob.glob('sources/*gcc*')[0]
    mingw = glob.glob('sources/*mingw*')[0]
    
    print('   Configuring binutils...')
    p = subprocess.Popen(f'../../{binutils}/configure --target={target} --prefix={os.path.abspath(prefix)} --with-sysroot={os.path.abspath(prefix)} --disable-nls --disable-werror --without-zstd', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-binutils-{target}/',
                         shell=True)
    get_subprocess_output(p)
    
    print('   Building binutils...')
    p = subprocess.Popen(f'gmake -j16', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-binutils-{target}/',
                         shell=True)
    get_subprocess_output(p)
    
    print('   Installing binutils...')
    p = subprocess.Popen(f'gmake install-strip', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-binutils-{target}/',
                         shell=True)
    get_subprocess_output(p)
   
    print('  Configuring mingw headers...')
    p = subprocess.Popen(f'../../{mingw}/mingw-w64-headers/configure --host={target} --prefix={os.path.abspath(prefix)}/{target}', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-mingw-headers-{target}/',
                         shell=True)
    get_subprocess_output(p)
    
    print('   Installing mingw headers...')
    p = subprocess.Popen(f'gmake install', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-mingw-headers-{target}/',
                         shell=True)
    get_subprocess_output(p)

    print('   Creating symlink...')
    p = subprocess.Popen(f'ln -s {os.path.abspath(prefix)}/{target} {os.path.abspath(prefix)}/mingw', shell=True)

    print('   Download prerequisites...')
    p = subprocess.Popen(f'contrib/download_prerequisites', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd = f'{gcc}',
                         shell=True)
    get_subprocess_output(p)

    print('   Configuring gcc...')
    p = subprocess.Popen(f'../../{gcc}/configure --target={target} --with-sysroot={os.path.abspath(prefix)} --with-ld={os.path.abspath(prefix)}/bin/{target}-ld --with-as={os.path.abspath(prefix)}/bin/{target}-as --prefix={os.path.abspath(prefix)} --without-zstd --disable-nls --disable-multilib --disable-werror --enable-languages=c,c++ --enable-threads=posix', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-gcc-{target}/',
                         shell=True)
    get_subprocess_output(p)

    print('   Building gcc...')
    p = subprocess.Popen(f'gmake all-gcc -j16', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-gcc-{target}/',
                         shell=True)
    get_subprocess_output(p)

    print('   Installing gcc...')
    p = subprocess.Popen(f'gmake install-strip-gcc', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-gcc-{target}/',
                         shell=True)
    get_subprocess_output(p)

    env_copy = env.copy()
    env_copy['CC'] = f'{target}-gcc'
    env_copy['CXX'] = f'{target}-g++'
    env_copy['CPP'] = f'{target}-cpp'

    print('  Configuring mingw...')
    p = subprocess.Popen(f'../../{mingw}/mingw-w64-crt/configure --host={target} --prefix={os.path.abspath(prefix)}/{target} --with-sysroot={os.path.abspath(prefix)}/{target} --disable-multilib', 
                         stdout=subprocess.PIPE, 
                         env=env_copy,
                         cwd=f'build/build-mingw-libs-{target}/',
                         shell=True)
    get_subprocess_output(p)
  
    print('  Building mingw...')
    p = subprocess.Popen(f'gmake -j16', 
                         stdout=subprocess.PIPE, 
                         env=env_copy,
                         cwd=f'build/build-mingw-libs-{target}/',
                         shell=True)
    get_subprocess_output(p)
  
    print('  Installing mingw...')
    p = subprocess.Popen(f'gmake install-strip', 
                         stdout=subprocess.PIPE, 
                         env=env_copy,
                         cwd=f'build/build-mingw-libs-{target}/',
                         shell=True)
    get_subprocess_output(p)

    print('  Configuring mingw winpthreads...')
    p = subprocess.Popen(f'../../{mingw}/mingw-w64-libraries/winpthreads/configure --host={target} --with-sysroot={os.path.abspath(prefix)}/{target} --prefix={os.path.abspath(prefix)}/{target}', 
                         stdout=subprocess.PIPE, 
                         env=env_copy,
                         cwd=f'build/build-mingw-winpthreads-{target}/',
                         shell=True)
    get_subprocess_output(p)
  
    print('  Building mingw winpthreads...')
    p = subprocess.Popen(f'gmake -j16', 
                         stdout=subprocess.PIPE, 
                         env=env_copy,
                         cwd=f'build/build-mingw-winpthreads-{target}/',
                         shell=True)
    get_subprocess_output(p)
  
    print('  Installing mingw winpthreads...')
    p = subprocess.Popen(f'gmake install-strip', 
                         stdout=subprocess.PIPE, 
                         env=env_copy,
                         cwd=f'build/build-mingw-winpthreads-{target}/',
                         shell=True)
    get_subprocess_output(p)
    
    print('  Building gcc libs...')   
    p = subprocess.Popen(f'gmake -j16', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-gcc-{target}/',
                         shell=True)
    get_subprocess_output(p)

    print('   Installing gcc libs...')
    p = subprocess.Popen(f'gmake install-strip', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-gcc-{target}/',
                         shell=True)
    get_subprocess_output(p)
 
def cleanup():
    shutil.rmtree('build', ignore_errors=True)
    shutil.rmtree('sources', ignore_errors=True)
    shutil.rmtree('tarballs', ignore_errors=True)

def build_elf_toolchain(prefix):
    target = 'x86_64-elf'
    env = get_build_env(prefix, '', '', target)

    os.makedirs(f'build/build-binutils-{target}', exist_ok=True)
    os.makedirs(f'build/build-gdb-{target}', exist_ok=True)
    os.makedirs(f'build/build-gcc-{target}', exist_ok=True)

    binutils = glob.glob('sources/*binutils*')[0]
    gdb = glob.glob('sources/*gdb*')[0]
    gcc = glob.glob('sources/*gcc*')[0]
    
    print('   Configuring binutils...')
    p = subprocess.Popen(f'../../{binutils}/configure --target={target} --prefix={os.path.abspath(prefix)} --disable-nls --disable-werror --without-zstd', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-binutils-{target}/',
                         shell=True)
    get_subprocess_output(p)
    
    print('   Building binutils...')
    p = subprocess.Popen(f'gmake -j16', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-binutils-{target}/',
                         shell=True)
    get_subprocess_output(p)
    
    print('   Installing binutils...')
    p = subprocess.Popen(f'gmake install-strip', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-binutils-{target}/',
                         shell=True)
    get_subprocess_output(p)

    print('   Download prerequisites...')
    p = subprocess.Popen(f'contrib/download_prerequisites', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd = f'{gcc}',
                         shell=True)
    get_subprocess_output(p)
  
    print('   Configuring gcc...')
    p = subprocess.Popen(f'../../{gcc}/configure --target={target} --prefix={os.path.abspath(prefix)} --disable-nls --disable-multilib --disable-werror --disable-libstdcxx --without-zstd --without-headers --without-newlib --enable-languages=c,c++', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-gcc-{target}/',
                         shell=True)
    get_subprocess_output(p)

    print('   Building gcc...')
    p = subprocess.Popen(f'gmake all-gcc -j16', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-gcc-{target}/',
                         shell=True)
    get_subprocess_output(p)

    print('   Installing gcc...')
    p = subprocess.Popen(f'gmake install-strip-gcc', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-gcc-{target}/',
                         shell=True)
    get_subprocess_output(p)
    
    print('  Building gcc libs...')   
    p = subprocess.Popen(f'gmake all-target-libgcc CFLAGS_FOR_TARGET=\'-g -O2 -mno-red-zone\' -j16', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-gcc-{target}/',
                         shell=True)
    get_subprocess_output(p)

    print('   Installing gcc libs...')
    p = subprocess.Popen(f'gmake install-target-libgcc', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-gcc-{target}/',
                         shell=True)
    get_subprocess_output(p)
    
    print('   Installing gmp...')
    p = subprocess.Popen(f'gmake install-strip', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-gcc-{target}/gmp',
                         shell=True)
    get_subprocess_output(p)
    
    print('   Installing mpfr...')
    p = subprocess.Popen(f'gmake install-strip', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-gcc-{target}/mpfr',
                         shell=True)
    get_subprocess_output(p)

    print('   Installing mpc...')
    p = subprocess.Popen(f'gmake install-strip', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-gcc-{target}/mpc',
                         shell=True)
    get_subprocess_output(p)

    print('   Configuring gdb...')
    p = subprocess.Popen(f'../../{gdb}/configure --target={target} --prefix={os.path.abspath(prefix)} --with-gmp={os.path.abspath(prefix)} --with-mpfr={os.path.abspath(prefix)} --without-zstd --disable-nls --disable-werror', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-gdb-{target}/',
                         shell=True)
    get_subprocess_output(p)

    print('   Building gdb...')
    p = subprocess.Popen(f'gmake all-gdb -j16', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-gdb-{target}/',
                         shell=True)
    get_subprocess_output(p)

    print('   Installing gdb...')
    p = subprocess.Popen(f'gmake install-gdb', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-gdb-{target}/',
                         shell=True)
    get_subprocess_output(p)

def build_win_mingw(prefix, mingw_prefix):
    target = 'x86_64-w64-mingw32'
    env = get_build_env(prefix, mingw_prefix, '', target)

    os.makedirs(f'build/build-win-binutils-{target}', exist_ok=True)
    os.makedirs(f'build/build-win-gcc-{target}', exist_ok=True)
    os.makedirs(f'build/build-win-mingw-headers-{target}', exist_ok=True)
    os.makedirs(f'build/build-win-mingw-libs-{target}', exist_ok=True)
    os.makedirs(f'build/build-win-mingw-winpthreads-{target}', exist_ok=True)

    binutils = glob.glob('sources/*binutils*')[0]
    gcc = glob.glob('sources/*gcc*')[0]
    mingw = glob.glob('sources/*mingw*')[0]
    
    print('   Configuring binutils...')
    p = subprocess.Popen(f'../../{binutils}/configure --host={target} --target={target} --prefix={os.path.abspath(prefix)} --disable-multilib --disable-nls --disable-werror --without-zstd', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-win-binutils-{target}/',
                         shell=True)
    get_subprocess_output(p)
    
    print('   Building binutils...')
    p = subprocess.Popen(f'gmake -j16', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-win-binutils-{target}/',
                         shell=True)
    get_subprocess_output(p)
    
    print('   Installing binutils...')
    p = subprocess.Popen(f'gmake install-strip', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-win-binutils-{target}/',
                         shell=True)
    get_subprocess_output(p)

    print('   Download prerequisites...')
    p = subprocess.Popen(f'contrib/download_prerequisites', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd = f'{gcc}',
                         shell=True)
    get_subprocess_output(p)

    print('   Configuring gcc...')
    p = subprocess.Popen(f'../../{gcc}/configure --host={target} --target={target} --prefix={os.path.abspath(prefix)} --disable-nls --disable-multilib --disable-werror --without-headers --without-newlib --enable-languages=c', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-win-gcc-{target}/',
                         shell=True)
    get_subprocess_output(p)

    print('   Building gcc...')
    p = subprocess.Popen(f'gmake -j16', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-win-gcc-{target}/',
                         shell=True)
    get_subprocess_output(p)

    print('   Installing gcc...')
    p = subprocess.Popen(f'gmake install-strip', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-win-gcc-{target}/',
                         shell=True)
    get_subprocess_output(p)

    print('  Copying libgcc to bin...')
    p = subprocess.Popen(f'cp {os.path.abspath(prefix)}/lib/libgcc_s_seh-1.dll {os.path.abspath(prefix)}/bin/', shell=True)
    p.wait()

    print('  Configuring mingw...')
    p = subprocess.Popen(f'../../{mingw}/configure --host={target} --prefix={os.path.abspath(prefix)}/{target} --with-libraries=winpthread --disable-multilib', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-mingw-libs-{target}/',
                         shell=True)
    get_subprocess_output(p)
  
    print('  Building mingw...')
    p = subprocess.Popen(f'gmake -j16', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-mingw-libs-{target}/',
                         shell=True)
    get_subprocess_output(p)
  
    print('  Installing mingw...')
    p = subprocess.Popen(f'gmake install-strip', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-mingw-libs-{target}/',
                         shell=True)
    get_subprocess_output(p)

    print('  Copying libwinpthread to bin...')
    p = subprocess.Popen(f'cp {os.path.abspath(prefix)}/{target}/bin/libwinpthread-1.dll {os.path.abspath(prefix)}/bin/', shell=True)
    p.wait()

    print('   Installing gmp...')
    p = subprocess.Popen(f'gmake install-strip', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-win-gcc-{target}/gmp',
                         shell=True)
    get_subprocess_output(p)
    
    print('   Installing mpfr...')
    p = subprocess.Popen(f'gmake install-strip', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-win-gcc-{target}/mpfr',
                         shell=True)
    get_subprocess_output(p)

    print('   Installing mpc...')
    p = subprocess.Popen(f'gmake install-strip', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-win-gcc-{target}/mpc',
                         shell=True)
    get_subprocess_output(p)

def build_win_elf(prefix, mingw_prefix, elf_prefix, win_mingw_prefix):
    host = 'x86_64-w64-mingw32'
    target = 'x86_64-elf'
    env = get_build_env(prefix, mingw_prefix, elf_prefix, target)

    os.makedirs(f'build/build-win-elf-binutils-{target}', exist_ok=True)
    os.makedirs(f'build/build-win-elf-gdb-{target}', exist_ok=True)
    os.makedirs(f'build/build-win-elf-gcc-{target}', exist_ok=True)

    binutils = glob.glob('sources/*binutils*')[0]
    gdb = glob.glob('sources/*gdb*')[0]
    gcc = glob.glob('sources/*gcc*')[0]
    
    print('   Configuring binutils...')
    p = subprocess.Popen(f'../../{binutils}/configure --host={host} --target={target} --prefix={os.path.abspath(prefix)} --disable-nls --disable-werror --without-zstd', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-win-elf-binutils-{target}/',
                         shell=True)
    get_subprocess_output(p)
    
    print('   Building binutils...')
    p = subprocess.Popen(f'gmake -j16', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-win-elf-binutils-{target}/',
                         shell=True)
    get_subprocess_output(p)
    
    print('   Installing binutils...')
    p = subprocess.Popen(f'gmake install-strip', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-win-elf-binutils-{target}/',
                         shell=True)
    get_subprocess_output(p)

    print('   Download prerequisites...')
    p = subprocess.Popen(f'contrib/download_prerequisites', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd = f'{gcc}',
                         shell=True)
    get_subprocess_output(p)
  
    print('   Configuring gcc...')
    p = subprocess.Popen(f'../../{gcc}/configure --host={host} --target={target} --prefix={os.path.abspath(prefix)} --disable-nls --disable-multilib --disable-werror --disable-libstdcxx --without-zstd --without-headers --without-newlib --enable-languages=c,c++', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-win-elf-gcc-{target}/',
                         shell=True)
    get_subprocess_output(p)

    print('   Building gcc...')
    p = subprocess.Popen(f'gmake all-gcc -j16', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-win-elf-gcc-{target}/',
                         shell=True)
    get_subprocess_output(p)

    print('   Installing gcc...')
    p = subprocess.Popen(f'gmake install-strip-gcc', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-win-elf-gcc-{target}/',
                         shell=True)
    get_subprocess_output(p)
    
    print('  Building gcc libs...')   
    p = subprocess.Popen(f'gmake all-target-libgcc CFLAGS_FOR_TARGET=\'-g -O2 -mno-red-zone\' -j16', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-win-elf-gcc-{target}/',
                         shell=True)
    get_subprocess_output(p)

    print('   Installing gcc libs...')
    p = subprocess.Popen(f'gmake install-target-libgcc', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-win-elf-gcc-{target}/',
                         shell=True)
    get_subprocess_output(p)
    
    print('   Configuring gdb...')
    p = subprocess.Popen(f'../../{gdb}/configure --host={host} --target={target} --prefix={os.path.abspath(prefix)} --with-gmp={os.path.abspath(win_mingw_prefix)} --with-mpfr={os.path.abspath(win_mingw_prefix)} --without-zstd --disable-nls --disable-werror', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-win-elf-gdb-{target}/',
                         shell=True)
    get_subprocess_output(p)

    print('   Building gdb...')
    p = subprocess.Popen(f'gmake all-gdb -j16', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-win-elf-gdb-{target}/',
                         shell=True)
    get_subprocess_output(p)

    print('   Installing gdb...')
    p = subprocess.Popen(f'gmake install-gdb', 
                         stdout=subprocess.PIPE, 
                         env=env,
                         cwd=f'build/build-win-elf-gdb-{target}/',
                         shell=True)
    get_subprocess_output(p)

def pack_compiler(archive_prefix, prefix, arch, platform, binfmt):
    xz_file = lzma.LZMAFile(os.path.join(archive_prefix, f'{arch}-{platform}-{binfmt}-gcc.tar.xz'), 'w')
    tar_file = TarFile.open(mode='w', fileobj=xz_file)
    for filename in os.listdir(prefix):
        path = os.path.join(prefix, filename)
        tar_file.add(os.path.join(prefix, filename), arcname=os.path.basename(path))
    xz_file.close()

def main():
    warnings.filterwarnings('ignore')

    parser = argparse.ArgumentParser(
        prog = 'build_linux_mac',
        description='Build GCC for Linux and MacOS'
    )

    parser.add_argument('--build_mingw', action='store_true', default=False)
    parser.add_argument('--build_elf', action='store_true', default=False)
    parser.add_argument('--build_win_mingw', action='store_true', default=False)
    parser.add_argument('--build_win_elf', action='store_true', default=False)

    parser.add_argument('--pack_mingw', action='store_true', default=False)
    parser.add_argument('--pack_elf', action='store_true', default=False)
    parser.add_argument('--pack_win_mingw', action='store_true', default=False)
    parser.add_argument('--pack_win_elf', action='store_true', default=False)

    parser.add_argument('--cleanup', action='store_true', default=False)
    parser.add_argument('-config', '--config', required=True, type=str, help="Configuration JSON, see example")

    args = vars(parser.parse_args())

    f = open(args['config'])
    config = json.load(f)
    f.close()

    if args['cleanup']:
        print('Cleanup...')
        cleanup()
        print('Done.')
        return

    if not os.path.isdir('tarballs'):
        print('Downloading sources:')
        download_sources(config['binutils'], config['gdb'], config['gcc'], config['mingw'])
        print('Done.')

    if not os.path.isdir('sources'):
        print('Extracting sources...')
        extract_sources()
        print('Done.')

    if args['build_mingw']:
        print('Building MinGW toolchain...')
        build_mingw_toolchain(config['mingw_prefix'])
        print('Done.')

    if args['build_elf']:
        print('Building ELF toolchain...')
        build_elf_toolchain(config['elf_prefix'])
        print('Done.')

    if args['build_win_mingw']:
        print('Building Windows MinGW toolchain...')
        build_win_mingw(config['mingw_win_prefix'], config['mingw_prefix'])
        print('Done.')

    if args['build_win_elf']:
        print('Building Windows ELF toolchain...')
        build_win_elf(config['elf_win_prefix'], config['mingw_prefix'], config['elf_prefix'], config['mingw_win_prefix'])
        print('Done.')
    
    os_name = str(platform.system()).lower()
    arch = str(platform.machine()).lower()

    if args['pack_mingw']:
        os.makedirs(config['archive_prefix'], exist_ok=True)
        print(f'Packing MinGW for {arch}-{os_name}')
        pack_compiler(config['archive_prefix'], config['mingw_prefix'], arch, os_name, 'mingw')
        print('Done.')

    if args['pack_elf']:
        os.makedirs(config['archive_prefix'], exist_ok=True)
        print(f'Packing ELF for {arch}-{os_name}')
        pack_compiler(config['archive_prefix'], config['elf_prefix'], arch, os_name, 'elf')
        print('Done.')
    
    if args['pack_win_mingw']:
        os.makedirs(config['archive_prefix'], exist_ok=True)
        print(f'Packing MinGW for amd64-windows')
        pack_compiler(config['archive_prefix'], config['mingw_win_prefix'], 'amd64', 'windows', 'mingw')
        print('Done.')

    if args['pack_win_elf']:
        os.makedirs(config['archive_prefix'], exist_ok=True)
        print(f'Packing ELF for amd64-windows')
        pack_compiler(config['archive_prefix'], config['elf_win_prefix'], 'amd64', 'windows', 'elf')
        print('Done.')

if __name__ == "__main__":
    main()
