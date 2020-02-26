###
# Copyright (c) 2020, Enrico
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

###

import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
try:
    from supybot.i18n import PluginInternationalization
    _ = PluginInternationalization('Weather')
except ImportError:
    # Placeholder that allows to run the plugin on a bot
    # without the i18n module
    _ = lambda x: x

from . import accuweather


def bailout(irc):
    irc.error("Weather plugin has committed suicide. x(")


class Weather(callbacks.Plugin):
    """Accuweather forecast and minutecast"""
    threaded = True

    @wrap(["channeldb", "text"])
    def weather(self, irc, msg, args, channel, location):
        """ <location>
        Accuweather forecast for <location> """

        lang = self.registryValue("defaultLang", channel)
        res = accuweather.forecast(location, lang=lang)

        if res:
            irc.reply("Weather ({0}): {1}".format(*res))
        else:
            bailout(irc)

    @wrap(["text"])
    def meteo(self, irc, msg, args, location):
        """ <location>
        Accuweather forecast for <location> """

        res = accuweather.forecast(location, lang="it")

        if res:
            irc.reply("Meteo ({0}): {1}".format(*res))
        else:
            bailout(irc)

    @wrap(["channeldb", "text"])
    def minutecast(self, irc, msg, args, channel, location):
        """ <location>
        Accuweather minutecast for <location> """

        # lang = self.registryValue("defaultLang", channel)
        res = accuweather.minutecast(location, lang="it")

        if res:
            irc.reply("Minutecast ({0}): {1}".format(*res))
        else:
            bailout(irc)

Class = Weather


# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79: