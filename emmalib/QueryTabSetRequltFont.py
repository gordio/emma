# -*- coding: utf-8 -*-
# emma
#
# Copyright (C) 2006 Florian Schmidt (flo@fastflo.de)
#               2014 Nickolay Karnaukhov (mr.electronick@gmail.com)
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301 USA

import gtk


class QueryTabSetResultFont:

    def __init__(self, query, emma):
        """
        @param query: QueryTab
        @param emma: Emma
        """
        self.emma = emma
        self.query = query
        button = self.query.xml.get_widget('query_result_font')
        button.connect('clicked', self.on_query_result_font_clicked)

    def on_query_result_font_clicked(self, button):
        d = self.emma.assign_once("query result font", gtk.FontSelectionDialog, "select result font")
        d.set_font_name(self.emma.config.get("query_result_font"))
        answer = d.run()
        d.hide()
        if not answer == gtk.RESPONSE_OK:
            return
        font_name = d.get_font_name()
        self.query.set_result_font(font_name)
        self.emma.config.config["query_result_font"] = font_name
        self.emma.config.save()

