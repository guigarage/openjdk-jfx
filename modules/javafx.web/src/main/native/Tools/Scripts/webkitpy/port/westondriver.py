# Copyright (C) 2013 Zan Dobersek <zandobersek@gmail.com>
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
#     * Redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above
# copyright notice, this list of conditions and the following disclaimer
# in the documentation and/or other materials provided with the
# distribution.
#     * Neither the Google name nor the names of its
# contributors may be used to endorse or promote products derived from
# this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import logging
import os
import random
import time

from webkitpy.port.server_process import ServerProcess
from webkitpy.port.driver import Driver
from webkitpy.port.xvfbdriver import XvfbDriver

_log = logging.getLogger(__name__)


class WestonDriver(Driver):
    @staticmethod
    def check_driver(port):
        weston_findcmd = ['which', 'weston']
        if port._should_use_jhbuild():
            weston_findcmd = port._jhbuild_wrapper + weston_findcmd
        weston_found = port.host.executive.run_command(weston_findcmd, return_exit_code=True) is 0
        if not weston_found:
            _log.error("No weston found. Cannot run layout tests.")
        return weston_found

    def __init__(self, *args, **kwargs):
        Driver.__init__(self, *args, **kwargs)
        self._startup_delay_secs = 1.0
        self._xvfbdriver = XvfbDriver(*args, **kwargs)

    def _setup_environ_for_test(self):
        driver_environment = self._port.setup_environ_for_server(self._server_name)
        driver_environment['DISPLAY'] = ":%d" % self._xvfbdriver._xvfb_run(driver_environment)
        weston_socket = 'WKTesting-weston-%032x' % random.getrandbits(128)
        weston_command = ['weston', '--socket=%s' % weston_socket, '--width=1024', '--height=768', '--use-pixman']
        if self._port._should_use_jhbuild():
            weston_command = self._port._jhbuild_wrapper + weston_command
        with open(os.devnull, 'w') as devnull:
            self._weston_process = self._port.host.executive.popen(weston_command, stderr=devnull, env=driver_environment)

        # Give Weston a bit of time to set itself up.
        time.sleep(self._startup_delay_secs)

        driver_environment['LOCAL_RESOURCE_ROOT'] = self._port.layout_tests_dir()
        if self._driver_tempdir is not None:
        # Currently on WebKit2, there is no API for setting the application cache directory.
        # Each worker should have its own and it should be cleaned afterwards, when the worker stops.
            driver_environment['XDG_CACHE_HOME'] = self._port.host.filesystem.join(str(self._driver_tempdir), 'appcache')
            driver_environment['DUMPRENDERTREE_TEMP'] = str(self._driver_tempdir)
        driver_environment['WAYLAND_DISPLAY'] = weston_socket
        driver_environment['GDK_BACKEND'] = 'wayland'
        if driver_environment.get('DISPLAY'):
            del driver_environment['DISPLAY']
        return driver_environment

    def _start(self, pixel_tests, per_test_args):
        self.stop()
        self._driver_tempdir = self._port._driver_tempdir(self._target_host)
        self._crashed_process_name = None
        self._crashed_pid = None
        self._server_process = self._port._server_process_constructor(self._port, self._server_name, self.cmd_line(pixel_tests, per_test_args), self._setup_environ_for_test())
        self._server_process.start()

    def stop(self):
        super(WestonDriver, self).stop()
        if getattr(self, '_weston_process', None):
            # The Weston process is terminated instead of killed, giving the Weston a chance to clean up after itself.
            self._weston_process.terminate()
            self._weston_process = None

