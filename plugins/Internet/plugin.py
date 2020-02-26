###
# Copyright (c) 2003-2005, Jeremiah Fincher
# Copyright (c) 2010-2011, James McCoy
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

import time
import socket
import telnetlib

import re
import urllib.request
import urllib.error
import html
from bs4 import BeautifulSoup as BS, SoupStrainer

import supybot.conf as conf
import supybot.utils as utils
import supybot.ircmsgs as ircmsgs
import supybot.ircutils as ircutils
import supybot.plugins as plugins
import supybot.callbacks as callbacks
from supybot.commands import *
from supybot.utils.iter import any as supyany
from supybot.i18n import PluginInternationalization, internationalizeDocstring
_ = PluginInternationalization('Internet')

from . import htmlcolors

class Internet(callbacks.Plugin):
    """Provides commands to query DNS, search WHOIS databases,
    and convert IPs to hex."""
    threaded = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._urlsnarf_re = re.compile(r'(https?://\S+\.\S{2,})')
        self._supported_content = ["text/html"]
        self._last_url = dict()
        self._last_tweet_url = dict()
        self._http_codes = dict()
        self._fill_http_codes()

    def _urlget(self, url, *, data=None, override_ua=True):
        req = urllib.request.Request(url)
        if override_ua is True:
            req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; WOW64; rv:51.0) Gecko/20100101 Firefox/51.0")
        
        urlh = urllib.request.urlopen(req, data)
    
        if urlh.code != 200:
            desc, _ = self._http_codes[urlh.code]
            raise urllib.error.HTTPError(url=url, code=urlh.code, msg=desc, hdrs=data, fp=urlh)
        else:
            return urlh

    def _fill_http_codes(self):
        urlh = self._urlget("https://www.w3.org/Protocols/rfc2616/rfc2616-sec10.html")
        soup = BS(urlh, parseOnlyThese=SoupStrainer("h3"))

        category = "Unknown"
        for entity in soup.findAll("h3"):
            content = entity.contents[1].strip()
            code, desc = content.split(" ", 1)
            try:
                code = int(code)
            except ValueError:
                category = content
            else:
                self._http_codes[code] = (desc, category)

    @internationalizeDocstring
    def dns(self, irc, msg, args, host):
        """<host|ip>

        Returns the ip of <host> or the reverse DNS hostname of <ip>.
        """
        banned_octets = ('192', '172', '127', '10')
        if utils.net.isIP(host):
            hostname = socket.getfqdn(host)
            host8 = host.split('.')[0]
            if hostname == host or host8 in banned_octets:
                irc.reply(_('Host not found.'))
            else:
                irc.reply(hostname)
        else:
            try:
                ips = socket.getaddrinfo(host, None)
                ips = map(lambda x:x[4][0], ips)
                ordered_unique_ips = []
                unique_ips = set()
                for ip in ips:
                    if ip not in unique_ips:
                        ordered_unique_ips.append(ip)
                        unique_ips.add(ip)
                irc.reply(format('%L', ordered_unique_ips))
            except socket.error:
                irc.reply(_('Host not found.'))
    dns = wrap(dns, ['something'])

    _domain = ['Domain Name', 'Server Name', 'domain']
    _netrange = ['NetRange', 'inetnum']
    _registrar = ['Sponsoring Registrar', 'Registrar', 'source']
    _netname = ['NetName', 'inetname']
    _updated = ['Last Updated On', 'Domain Last Updated Date', 'Updated Date',
                'Last Modified', 'changed', 'last-modified']
    _created = ['Created On', 'Domain Registration Date', 'Creation Date',
                'created', 'RegDate']
    _expires = ['Expiration Date', 'Domain Expiration Date']
    _status = ['Status', 'Domain Status', 'status']
    @internationalizeDocstring
    def whois(self, irc, msg, args, domain):
        """<domain>

        Returns WHOIS information on the registration of <domain>.
        """
        if utils.net.isIP(domain):
            whois_server = 'whois.arin.net'
            usertld = 'ipaddress'
        elif '.' in domain:
            usertld = domain.split('.')[-1]
            whois_server = '%s.whois-servers.net' % usertld
        else:
            usertld = None
            whois_server = 'whois.iana.org'
        try:
            sock = utils.net.getSocket(whois_server,
                    vhost=conf.supybot.protocols.irc.vhost(),
                    vhostv6=conf.supybot.protocols.irc.vhostv6(),
                    )
            sock.connect((whois_server, 43))
        except socket.error as e:
            irc.error(str(e))
            return
        sock.settimeout(5)
        if usertld == 'com':
            sock.send(b'=')
        elif usertld == 'ipaddress':
            sock.send(b'n + ')
        sock.send(domain.encode('ascii'))
        sock.send(b'\r\n')

        s = b''
        end_time = time.time() + 5
        try:
            while end_time>time.time():
                time.sleep(0.1)
                s += sock.recv(4096)
        except socket.error:
            pass
        sock.close()
        server = netrange = netname = registrar = updated = created = expires = status = ''
        for line in s.splitlines():
            line = line.decode('utf8').strip()
            if not line or ':' not in line:
                continue
            if not server and supyany(line.startswith, self._domain):
                server = ':'.join(line.split(':')[1:]).strip().lower()
                # Let's add this check so that we don't respond with info for
                # a different domain. E.g., doing a whois for microsoft.com
                # and replying with the info for microsoft.com.wanadoodoo.com
                if server != domain:
                    server = ''
                    continue
            if not netrange and supyany(line.startswith, self._netrange):
                netrange = ':'.join(line.split(':')[1:]).strip()
            if not server and not netrange:
                continue
            if not registrar and supyany(line.startswith, self._registrar):
                registrar = ':'.join(line.split(':')[1:]).strip()
            elif not netname and supyany(line.startswith, self._netname):
                netname = ':'.join(line.split(':')[1:]).strip()
            elif not updated and supyany(line.startswith, self._updated):
                s = ':'.join(line.split(':')[1:]).strip()
                updated = _('updated %s') % s
            elif not created and supyany(line.startswith, self._created):
                s = ':'.join(line.split(':')[1:]).strip()
                created = _('registered %s') % s
            elif not expires and supyany(line.startswith, self._expires):
                s = ':'.join(line.split(':')[1:]).strip()
                expires = _('expires %s') % s
            elif not status and supyany(line.startswith, self._status):
                status = ':'.join(line.split(':')[1:]).strip().lower()
        if not status:
            status = 'unknown'
        try:
            t = telnetlib.Telnet('whois.pir.org', 43)
        except socket.error as e:
            irc.error(str(e))
            return
        t.write(b'registrar ')
        t.write(registrar.split('(')[0].strip().encode('ascii'))
        t.write(b'\n')
        s = t.read_all()
        url = ''
        for line in s.splitlines():
            line = line.decode('ascii').strip()
            if not line:
                continue
            if line.startswith('Email'):
                url = _(' <registered at %s>') % line.split('@')[-1]
            elif line.startswith('Registrar Organization:'):
                url = _(' <registered by %s>') % line.split(':')[1].strip()
            elif line == 'Not a valid ID pattern':
                url = ''
        if (server or netrange) and status:
            entity = server or 'Net range %s%s' % \
                    (netrange, ' (%s)' % netname if netname else '')
            info = filter(None, [status, created, updated, expires])
            s = format(_('%s%s is %L.'), entity, url, info)
            irc.reply(s)
        else:
            irc.error(_('I couldn\'t find such a domain.'))
    whois = wrap(whois, ['lowered'])

    @internationalizeDocstring
    def hexip(self, irc, msg, args, ip):
        """<ip>

        Returns the hexadecimal IP for that IP.
        """
        ret = ""
        if utils.net.isIPV4(ip):
            quads = ip.split('.')
            for quad in quads:
                i = int(quad)
                ret += '%02X' % i
        else:
            octets = ip.split(':')
            for octet in octets:
                if octet:
                    i = int(octet, 16)
                    ret += '%04X' % i
                else:
                    missing = (8 - len(octets)) * 4
                    ret += '0' * missing
        irc.reply(ret)
    hexip = wrap(hexip, ['ip'])

    def _address_or_lasturl(self, address, last_url):
        if not address and not last_url:
            return

        if address:
            for prefix in ("", "https://", "http://"):
                s = prefix + address
                res = self._urlsnarf_re.match(ircutils.stripFormatting(s))
                if res:
                    address = res.group(1)
                    break
            else:
                raise urllib.error.URLError(reason="invalid url: '%s'" % address)

        return address or last_url

    @staticmethod
    def _read_chunked(urlh, chunksize=8192):
        buf = b''

        while True:
            data = urlh.read(chunksize)
            if data == b'':
                break
            buf += data

            yield buf

    def _title(self, url):
        urlh = self._urlget(url, override_ua=False)

        info = urlh.info()
        if info.get_content_type() not in self._supported_content:
            s = "(%s): Content-Type: %s - Content-Length: %s"
            return s % (utils.str.shorten(url), info["Content-Type"], info["Content-Length"])

        #soup = BS(urlh, parse_only=SoupStrainer('title', limit=1))
        #if soup.text:
        #    title_text = html.unescape(soup.text)
        #    return "Title (%s): %s" % (utils.str.shorten(url), title_text)

        for webpage in self._read_chunked(urlh):
            mtch = re.search(b"<title>(.+)</title>", webpage, re.DOTALL)
            if mtch:
                try:
                    charset = info.get_charsets()[0] or "utf8"
                except IndexError:
                    charset = "ascii"

                match_text = mtch.group(1)
                title_text = html.unescape(match_text.strip().decode(charset))

                return "Title (%s): %s" % (utils.str.shorten(url), title_text)

    def _checkpoint(self):
        t = time.monotonic() - self._t

        self._t = time.monotonic()

        return t

    @wrap(['channeldb', optional('text')])
    def title(self, irc, msg, args, channel, address):
        """ [url] """

        last_url = self._last_url.get(channel)
        url = self._address_or_lasturl(address, last_url)
        if url is None:
            return

        title = self._title(url)
        if title:
            irc.reply(title)

    def _tweet(self, url):
        urlh = self._urlget(url, override_ua=False)

        soup = BS(urlh)
        tweet_text = soup.find("p", {"class": "tweet-text"})
        if tweet_text and tweet_text.text != "":
            content = []

            for child in tweet_text:
                try:
                    if "u-hidden" not in child.attrs["class"]:
                        content.append(child.text)
                except AttributeError:
                    content.append(child)

            if not content:
                media = soup.find("div", {"class": "AdaptiveMedia-container"})
                if media:
                    img = media.find("img")
                    if img:
                        content.append(img["src"])

            if content:
                return "Tweet (%s): %s" % (utils.str.shorten(url), "".join(content))

    @wrap(['channeldb', optional('text')])
    def tweet(self, irc, msg, args, channel, address):
        """ [url] """
        last_url = self._last_tweet_url.get(channel)
        url = self._address_or_lasturl(address, last_url)

        if url is None:
            return

        tweet = self._tweet(url)
        tweet = re.sub(r"\n+", " | ", tweet)
        if tweet:
            irc.reply(tweet)

    @wrap(['channeldb'])
    def lasturl(self, irc, msg, args, channel):
        """ """
        if channel in self._last_url:
            irc.reply(self._last_url[channel], prefixNick=True)

    @wrap(['channeldb'])
    def lasttweet(self, irc, msg, args, channel):
        """ """
        if channel in self._last_tweet_url:
            irc.reply(self._last_tweet_url[channel], prefixNick=True)

    @wrap(['long'])
    def http(self, irc, msg, args, code):
        """<http_code> """
        try:
            desc, category = self._http_codes[code]
            irc.reply("%s, HTTP %d %s" % (category, code, desc), prefixNick=True)
        except KeyError:
            irc.error("unknown HTTP code: %d" % code)

    @wrap(["text"])
    def rgb(self, irc, msg, args, text):
        """<[#]xxxxxx>|<r, g, b>
        
        Returns the HTML color name or the closest color.
        """
        args = []
        color = text.split()

        try:
           if len(color) == 3:
                args = [int(c) for c in color]
           elif len(color) == 1:
                args = color
           else:
                raise ValueError
        except ValueError:
            irc.error("Invalid input: {}".format(color))
        else:
            irc.reply(htmlcolors.rgb(*args), prefixNick=True)

    def doPrivmsg(self, irc, msg):
        if not irc.isChannel(msg.args[0]):
            return
        channel = plugins.getChannel(msg.args[0])

        if callbacks.addressed(irc.nick, msg):
            return

        if ircmsgs.isAction(msg):
            text = ircmsgs.unAction(msg)
        elif not ircmsgs.isCtcp(msg):
            text = msg.args[1]
        else:
            return

        res = self._urlsnarf_re.search(ircutils.stripFormatting(text))
        if res:
            url = utils.str.try_coding(res.group(1))
            urlsplt = urllib.parse.urlsplit(url)

            if urlsplt.netloc.endswith("twitter.com"):
                self._last_tweet_url[channel] = url
            else:
                self._last_url[channel] = url

            if self.registryValue("ytAutoTitle", channel):
                isYtUrl = urlsplt.netloc in ("www.youtube.com", "youtube.com", "youtu.be")
                botNicks = self.registryValue("botNames", channel).split()
                isHumanBeing = not supyany(msg.nick.startswith, botNicks)

                if (urlsplt.path or urlsplt.query) and isYtUrl and isHumanBeing:
                    title = self._title(url)
                    if title:
                        irc.reply(title)

Internet = internationalizeDocstring(Internet)

Class = Internet


# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
