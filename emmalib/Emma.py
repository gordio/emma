import time
from stat import *
import gc
import pickle
import datetime
import bz2
import sql
import glib

import gtk
import gtk.gdk
from gtk import keysyms
import gtk.glade
import gobject

from query_regular_expression import *

from ConnectionTreeView import ConnectionsTreeView
from OutputHandler import OutputHandler
from Config import Config
from QueryTab import QueryTab
import dialogs
import widgets

from Constants import *


class Emma:
    def __init__(self):
        self.emma_path = emma_path
        self.sql = sql
        self.created_once = {}
        self.query_changed_listener = []
        self.stored_orders = {}
        self.query_count = 0
        self.glade_path = glade_path
        self.icons_path = icons_path
        self.glade_file = os.path.join(glade_path, "emma.glade")
        if not os.access(self.glade_file, os.R_OK):
            print self.glade_file, "not found!"
            sys.exit(-1)

        print "glade file: %r" % self.glade_file
        self.xml = gtk.glade.XML(self.glade_file)
        self.mainwindow = self.xml.get_widget("mainwindow")
        self.mainwindow.connect('destroy', lambda *args: gtk.main_quit())
        self.xml.signal_autoconnect(self)

        try:
            icon = gtk.gdk.pixbuf_new_from_file(os.path.join(icons_path, "emma.png"))
            self.mainwindow.set_icon(icon)
        except glib.GError:
            print "Icon not loaded"

        self.current_query = None

        # init dialogs
        self.about_dialog = dialogs.About()
        self.changelog_dialog = dialogs.ChangeLog(emma_path)
        self.execute_query_from_disk_dialog = False

        # init all notebooks
        self.message_notebook = self.xml.get_widget("message_notebook")
        self.main_notebook = self.xml.get_widget("main_notebook")
        self.query_notebook = self.xml.get_widget("query_notebook")

        # init Message log
        self.msg_log = widgets.TabMsgLog(self)
        self.message_notebook.prepend_page(self.msg_log, gtk.Label('Message Log'))

        # init SQL log
        self.sql_log = widgets.TabSqlLog(self)
        self.message_notebook.prepend_page(self.sql_log, gtk.Label('SQL Log'))

        self.blob_view = widgets.TabBlobView(self)
        self.message_notebook.append_page(self.blob_view, gtk.Label('Blob View'))

        # table view
        self.table_view = widgets.TabTable(self)
        self.main_notebook.prepend_page(self.table_view, gtk.Label('Table'))

        # process list
        self.tableslist = widgets.TabTablesList(self)
        self.main_notebook.prepend_page(self.tableslist, gtk.Label('Tables List'))

        # tables list
        self.processlist = widgets.TabProcessList(self)
        self.main_notebook.prepend_page(self.processlist, gtk.Label('Process List'))

        # Local Search Window
        self.local_search_window = self.xml.get_widget("localsearch_window")
        self.local_search_entry = self.xml.get_widget("local_search_entry")
        self.local_search_entry.connect("activate", lambda *a: self.local_search_window.response(gtk.RESPONSE_OK))
        self.local_search_start_at_first_row = self.xml.get_widget("search_start_at_first_row")
        self.local_search_case_sensitive = self.xml.get_widget("search_case_sensitive")

        self.clipboard = gtk.Clipboard(gtk.gdk.display_get_default(), "CLIPBOARD")
        self.pri_clipboard = gtk.Clipboard(gtk.gdk.display_get_default(), "PRIMARY")

        self.field_edit = self.xml.get_widget("field_edit")
        self.field_edit_content = self.xml.get_widget("edit_field_content")

        self.tooltips = gtk.Tooltips()
        self.sort_timer_running = False
        self.execution_timer_running = False
        self.field_conditions_initialized = False
        self.current_host = None

        self.hosts = {}
        self.queries = []

        self.config = Config(self)
        self.config.load()

        self.connections_tv_container = self.xml.get_widget("connections_tv_container")
        self.connections_tv = ConnectionsTreeView(self)
        self.connections_tv_container.add(self.connections_tv)
        self.connections_tv.show()

        self.add_query_tab(QueryTab(self.query_notebook, self))

        self.first_template = None
        # keys = self.config.config.keys()
        # keys.sort()
        #
        # toolbar = self.xml.get_widget("query_toolbar")
        # toolbar.set_style(gtk.TOOLBAR_ICONS)
        # for child in toolbar.get_children():
        #     if not child.name.startswith("template_"):
        #         continue
        #     toolbar.remove(child)

        # template_count = 0
        # for name in keys:
        #     value = self.config.config[name]
        #     if not self.config.unpickled:
        #         prefix = "connection_"
        #         if name.startswith(prefix) and value == "::sqlite::":
        #             filename = name[len(prefix):]
        #             self.add_sqlite(filename)
        #             continue
        #         if name.startswith(prefix):
        #             v = value.split(",")
        #             port = ""
        #             p = v[0].rsplit(":", 1)
        #             if len(p) == 2:
        #                 port = p[1]
        #                 v[0] = p[0]
        #             self.add_mysql_host(name[len(prefix):], v[0], port, v[1], v[2], v[3])
        #             pass
        #
        #     prefix = "template"
        #     if name.startswith(prefix):
        #         value = value.replace("`$primary_key$`", "$primary_key$")
        #         value = value.replace("`$table$`", "$table$")
        #         value = value.replace("`$field_conditions$`", "$field_conditions$")
        #         self.config.config[name] = value
        #         if not self.first_template:
        #             self.first_template = value
        #         p = name.split("_", 1)
        #         template_count += 1
        #
        #         button = gtk.ToolButton(gtk.STOCK_EXECUTE)
        #         button.set_name("template_%d" % template_count)
        #         button.set_tooltip(self.tooltips, "%s\n%s" % (p[1], value))
        #         button.connect("clicked", self.on_template, value)
        #         toolbar.insert(button, -1)
        #         button.show()

        # menu = self.xml.get_widget("query_encoding_menu")
        # for child in menu.get_children():
        #     menu.remove(child)

        # for coding, index_desc in enumerate(self.config.codings):
        #     item = gtk.MenuItem(coding, False)
        #     item.connect("activate", self.on_query_encoding_changed, (coding, index_desc(0)))
        #     menu.append(item)
        #     item.show()

        if int(self.config.get("ping_connection_interval")) > 0:
            gobject.timeout_add(
                int(self.config.get("ping_connection_interval")) * 1000,
                self.on_connection_ping
            )
        self.init_plugins()

    def __getattr__(self, name):
        widget = self.xml.get_widget(name)
        if widget is None:
            raise AttributeError(name)
        return widget

    def on_reload_plugins_activate(self, *args):
        self.unload_plugins()
        self.load_plugins()

    def init_plugin(self, plugin):
        try:
            plugin_init = getattr(plugin, "plugin_init")
        except:
            return True
        plugin_init(self)

    def unload_plugin(self, plugin):
        try:
            plugin_unload = getattr(plugin, "plugin_unload")
            return plugin_unload()
        except:
            return True

    def load_plugins(self):
        def _load(_plugin_name):
            print "loading plugin %r" % _plugin_name
            if _plugin_name in self.plugins:
                plugin = reload(self.plugins[_plugin_name])
            else:
                plugin = __import__(_plugin_name)
            self.plugins[_plugin_name] = plugin
            self.init_plugin(plugin)
        for path in self.plugin_pathes:
            for plugin_name in os.listdir(path):
                plugin_dir = os.path.join(path, plugin_name)
                if not os.path.isdir(plugin_dir) or plugin_name[0] == ".":
                    continue
                #try:
                _load(plugin_name)
                #except Exception as e:
                #    print "!!!could not load plugin %r" % plugin_name, e.message

    def unload_plugins(self):
        """ not really an unload - i just asks the module to cleanup """
        for plugin_name, plugin in self.plugins.iteritems():
            #print "unloading plugin", plugin_name, "...",
            self.unload_plugin(plugin)
            #print "done"

    def init_plugins(self):
        plugins_pathes = [
            # os.path.join(self.config.config_path, "plugins"),
            os.path.join(emma_path, "plugins")
        ]
        self.plugin_pathes = []
        self.plugins = {}
        for path in plugins_pathes:
            if not os.path.isdir(path):
                print "plugins-dir %r does not exist" % path
                continue
            if not path in sys.path:
                sys.path.insert(0, path)
            self.plugin_pathes.append(path)
        self.load_plugins()

    def add_query_tab(self, qt):
        self.query_count += 1
        self.current_query = qt
        self.queries.append(qt)
        qt.set_query_encoding(self.config.get("db_encoding"))
        qt.set_query_font(self.config.get("query_text_font"))
        qt.set_result_font(self.config.get("query_result_font"))
        if self.config.get_bool("query_text_wrap"):
            qt.set_wrap_mode(gtk.WRAP_WORD)
        else:
            qt.set_wrap_mode(gtk.WRAP_NONE)
        qt.set_current_host(self.current_host)

        tab_label_hbox = gtk.HBox()
        tab_label_label = gtk.Label('Query')
        tab_label_label.show()
        tab_label_ebox = gtk.EventBox()
        img = gtk.Image()
        img.set_from_stock(gtk.STOCK_CLOSE, 1)
        img.show()
        tab_label_ebox.add(img)
        tab_label_ebox.show()
        tab_label_ebox.connect('button_release_event', self.on_closequery_label_button_clicked)

        tab_label_hbox.pack_start(tab_label_label)
        tab_label_hbox.pack_end(tab_label_ebox)
        tab_label_hbox.show()

        self.query_notebook.append_page(qt.xml.get_widget('first_query'), tab_label_hbox)
        self.query_notebook.set_current_page(len(self.queries) - 1)
        self.current_query.textview.grab_focus()

    def on_closequery_label_button_clicked(self, button, event):
        self.on_closequery_button_clicked(None)

    def del_query_tab(self, qt):
        if self.current_query == qt:
            self.current_query = None

        i = self.queries.index(qt)
        del self.queries[i]

    def on_connection_ping(self):
        _iter = self.connections_tv.connections_model.get_iter_root()
        while _iter:
            host = self.connections_tv.connections_model.get_value(_iter, 0)
            if host.connected:
                if not host.ping():
                    print "...error! reconnect seems to fail!"
            _iter = self.connections_tv.connections_model.iter_next(_iter)
        return True

    def search_query_end(self, text, _start):
        try:
            r = self.query_end_re
        except:
            r = self.query_end_re = re.compile(r'("(?:[^\\]|\\.)*?")|(\'(?:[^\\]|\\.)*?\')|(`(?:[^\\]|\\.)*?`)|(;)')
        while 1:
            result = re.search(r, text[_start:])
            if not result:
                return None

            _start += result.end()
            if result.group(4):
                return _start

    def is_query_editable(self, query, result=None):
        table, where, field, value, row_iter = self.get_unique_where(query)
        if not table or not where:
            return False
        return True

    def is_query_appendable(self, query):
        pat = r'(?i)("(?:[^\\]|\\.)*?")|(\'(?:[^\\]|\\.)*?\')|(`(?:[^\\]|\\.)*?`)|(union)|(select[ \r\n\t]+(.*)[ \r\n\t]+from[ \r\n\t]+(.*))'
        if not self.current_host:
            return False
        try:
            r = self.query_select_re
        except:
            r = self.query_select_re = re.compile(pat)
        _start = 0
        result = False
        while 1:
            result = re.search(r, query[_start:])
            if not result:
                return False
            _start += result.end()
            if result.group(4):
                return False  # union
            if result.group(5) and result.group(6) and result.group(7):
                break  # found select
        return result

    def get_order_from_query(self, query, return_before_and_after=False):
        current_order = []
        try:
            r = self.query_order_re
        except:
            r = self.query_order_re = re.compile(re_src_query_order)
        # get current order by clause
        match = re.search(r, query)
        if not match:
            print "no order found in", [query]
            print "re:", [re_src_query_order]
            return current_order
        before, order, after = match.groups()
        order.lower()
        _start = 0
        ident = None
        while 1:
            item = []
            while 1:
                ident, end = self.read_expression(order[_start:])
                if not ident:
                    break
                if ident == ",":
                    break
                if ident[0] == "`":
                    ident = ident[1:-1]
                item.append(ident)
                _start += end
            l = len(item)
            if l == 0:
                break
            elif l == 1:
                item.append(True)
            elif l == 2:
                if item[1].lower() == "asc":
                    item[1] = True
                else:
                    item[1] = False
            else:
                print "unknown order item:", item, "ignoring..."
                item = None
            if item:
                current_order.append(tuple(item))
            if not ident:
                break
            _start += 1  # comma
        return current_order

    def get_field_list(self, s):
        # todo USE IT!
        fields = []
        _start = 0
        ident = None
        while 1:
            item = []
            while 1:
                ident, end = self.read_expression(s[_start:])
                if not ident:
                    break
                if ident == ",":
                    break
                if ident[0] == "`":
                    ident = ident[1:-1]
                item.append(ident)
                _start += end
            if len(item) == 1:
                fields.append(item[0])
            else:
                fields.append(item)
            if not ident:
                break
        print "found fields:", fields
        return fields

    def get_unique_where(self, query, path=None, col_num=None, return_fields=False):
        # call is_query_appendable before!
        result = self.is_query_appendable(query)
        if not result:
            return None, None, None, None, None

        field_list = result.group(6)
        table_list = result.group(7)

        # check tables
        table_list = table_list.replace(" join ", ",")
        table_list = re.sub("(?i)(?:order[ \t\r\n]by.*|limit.*|group[ \r\n\t]by.*|order[ \r\n\t]by.*|where.*)",
                            "", table_list)
        table_list = table_list.replace("`", "")
        tables = table_list.split(",")

        if len(tables) > 1:
            print "sorry, i can't edit queries with more than one than one source-table:", tables
            return None, None, None, None, None

        # get table_name
        table = tables[0].strip(" \r\n\t").strip("`'\"")
        print "table:", table

        # check for valid fields
        field_list = re.sub("[\r\n\t ]+", " ", field_list)
        field_list = re.sub("'.*?'", "__BAD__STRINGLITERAL", field_list)
        field_list = re.sub("\".*?\"", "__BAD__STRINGLITERAL", field_list)
        field_list = re.sub("\\(.*?\\)", "__BAD__FUNCTIONARGUMENTS", field_list)
        field_list = re.sub("\\|", "__PIPE__", field_list)
        temp_fields = field_list.split(",")
        fields = []
        for f in temp_fields:
            fields.append(f.strip("` \r\n\t"))
        print "fields:", fields

        wildcard = False
        for field in fields:
            if field.find("*") != -1:
                wildcard = True
                break

        # find table handle!
        tries = 0
        new_tables = []
        self.last_th = None
        while 1:
            try:
                th = self.current_host.current_db.tables[table]
                break
            except:
                tries += 1
                if tries > 1:
                    print "query not editable, because table %r is not found in db %r" % (table,
                                                                                          self.current_host.current_db)
                    return None, None, None, None, None
                new_tables = self.current_host.current_db.refresh()
                continue
        # does this field really exist in this table?
        c = 0
        possible_primary = possible_unique = ""
        unique = primary = ""
        pri_okay = uni_okay = 0

        for i in new_tables:
            self.current_host.current_db.tables[i].refresh(False)

        if not th.fields and not table in new_tables:
            th.refresh(False)

        row_iter = None
        if path:
            row_iter = self.current_query.model.get_iter(path)

        # get unique where_clause
        self._kv_list = []
        self.last_th = th
        for field, field_pos in zip(th.field_order, range(len(th.field_order))):
            props = th.fields[field]
            if (
                (pri_okay >= 0 and props[3] == "PRI") or (
                    th.host.__class__.__name__ == "sqlite_host" and field.endswith("_id"))):
                if possible_primary:
                    possible_primary += ", "
                possible_primary += field
                if wildcard:
                    c = field_pos
                else:
                    c = None
                    try:
                        c = fields.index(field)
                    except:
                        pass
                if not c is None:
                    pri_okay = 1
                    if path:
                        value = self.current_query.model.get_value(row_iter, c)
                        if primary:
                            primary += " and "
                        primary += "`%s`='%s'" % (field, value)
                        self._kv_list.append((field, value))
            if uni_okay >= 0 and props[3] == "UNI":
                if possible_unique:
                    possible_unique += ", "
                possible_unique += field
                if wildcard:
                    c = field_pos
                else:
                    c = None
                    try:
                        c = fields.index(field)
                    except:
                        pass
                if not c is None:
                    uni_okay = 1
                    if path:
                        value = self.current_query.model.get_value(row_iter, c)
                        if unique:
                            unique += " and "
                        unique += "`%s`='%s'" % (field, value)
                        self._kv_list.append((field, value))

        if uni_okay < 1 and pri_okay < 1:
            possible_key = "(i can't see any key-fields in this table...)"
            if possible_primary:
                possible_key = "e.g.'%s' would be useful!" % possible_primary
            elif possible_unique:
                possible_key = "e.g.'%s' would be useful!" % possible_unique
            print "no edit-key found. try to name a key-field in your select-clause. (%r)" % possible_key
            return table, None, None, None, None

        value = ""
        field = None
        if path:
            where = primary
            if not where:
                where = unique
            if not where:
                where = None
            if not col_num is None:
                value = self.current_query.model.get_value(row_iter, col_num)
                if wildcard:
                    field = th.field_order[col_num]
                else:
                    field = fields[col_num]
        else:
            where = possible_primary + possible_unique

        # get current edited field and value by col_num
        if return_fields:
            return table, where, field, value, row_iter, fields
        return table, where, field, value, row_iter

    def on_query_column_sort(self, column, col_num):
        query = self.current_query.last_source
        current_order = self.get_order_from_query(query)
        col = column.get_title().replace("__", "_")
        new_order = []
        for c, o in current_order:
            if c == col:
                if o:
                    new_order.append([col, False])
                col = None
            else:
                new_order.append([c, o])
        if col:
            new_order.append([self.current_host.escape_field(col), True])
        try:
            r = self.query_order_re
        except:
            r = self.query_order_re = re.compile(re_src_query_order)
        match = re.search(r, query)
        if match:
            before, order, after = match.groups()
            order = ""
            addition = ""
        else:
            match = re.search(re_src_after_order, query)
            if not match:
                before = query
                after = ""
            else:
                before = query[0:match.start()]
                after = match.group()
            addition = "\norder by\n\t"
        order = ""
        for col, o in new_order:
            if order:
                order += ",\n\t"
            order += self.current_host.escape_field(col)
            if not o:
                order += " desc"
        if order:
            new_query = ''.join([before, addition, order, after])
        else:
            new_query = re.sub("(?i)order[ \r\n\t]+by[ \r\n\t]+", "", before + after)
        self.current_query.set(new_query)

        if self.config.get("result_view_column_sort_timeout") <= 0:
            self.on_execute_query_clicked()

        new_order = dict(new_order)

        for col in self.current_query.treeview.get_columns():
            field_name = col.get_title().replace("__", "_")
            try:
                sort_col = new_order[field_name]
                col.set_sort_indicator(True)
                if sort_col:
                    col.set_sort_order(gtk.SORT_ASCENDING)
                else:
                    col.set_sort_order(gtk.SORT_DESCENDING)
            except:
                col.set_sort_indicator(False)

        if not self.sort_timer_running:
            self.sort_timer_running = True
            gobject.timeout_add(
                100 + int(self.config.get("result_view_column_sort_timeout")),
                self.on_sort_timer
            )
        self.sort_timer_execute = time.time() + int(self.config.get("result_view_column_sort_timeout")) / 1000.

    def on_sort_timer(self):
        if not self.sort_timer_running:
            return False
        if self.sort_timer_execute > time.time():
            return True
        self.sort_timer_running = False
        self.on_execute_query_clicked()
        return False

    def on_query_change_data(self, cellrenderer, path, new_value, col_num, force_update=False):
        q = self.current_query
        row_iter = q.model.get_iter(path)
        if q.append_iter \
                and q.model.iter_is_valid(q.append_iter) \
                and q.model.get_path(q.append_iter) == q.model.get_path(row_iter):
            q.filled_fields[q.treeview.get_column(col_num).get_title().replace("__", "_")] = new_value
            q.model.set_value(row_iter, col_num, new_value)
            return

        table, where, field, value, row_iter = self.get_unique_where(q.last_source, path, col_num)
        if force_update is False and new_value == value:
            return
        if self.current_host.__class__.__name__ == "sqlite_host":
            limit = ""
        else:
            limit = " limit 1"
        update_query = u"update %s set %s='%s' where %s%s" % (
            self.current_host.escape_table(table),
            self.current_host.escape_field(field),
            self.current_host.escape(new_value),
            where,
            limit
        )
        if self.current_host.query(update_query, encoding=q.encoding):
            print "set new value: %r" % new_value
            q.model.set_value(row_iter, col_num, new_value)
            return True
        return False

    def on_reload_self_activate(self, item):
        pass

    def on_message_notebook_switch_page(self, nb, pointer, page):
        if self.current_query:
            self.current_query.on_query_view_cursor_changed(self.current_query.treeview)

    def on_execute_query_from_disk_activate(self, button, filename=None):
        if not self.current_host:
            dialogs.show_message("execute query from disk", "no host selected!")
            return
        if not self.execute_query_from_disk_dialog:
            self.execute_query_from_disk_dialog = dialogs.ExecuteQueryFromDisk(self)
        self.execute_query_from_disk_dialog.show()

    def get_widget(self, name):
        return self.assign_once("widget_%s" % name, self.xml.get_widget, name)

    def read_query(self, query, _start=0):
        try:
            r = self.find_query_re
            rw = self.white_find_query_re
        except:
            r = self.find_query_re = re.compile(r"""
                (?s)
                (
                ("(?:[^\\]|\\.)*?")|            # double quoted strings
                ('(?:[^\\]|\\.)*?')|            # single quoted strings
                (`(?:[^\\]|\\.)*?`)|            # backtick quoted strings
                (/\*.*?\*/)|                    # c-style comments
                (\#[^\n]*)|                     # shell-style comments
                (\--[^\n]*)|                        # sql-style comments
                ([^;])                          # everything but a semicolon
                )+
            """, re.VERBOSE)
            rw = self.white_find_query_re = re.compile("[ \r\n\t]+")

        m = rw.match(query, _start)
        if m:
            _start = m.end(0)

        match = r.match(query, _start)
        if not match:
            return None, len(query)
        return match.start(0), match.end(0)

    def on_execute_query_clicked(self, button=None, query=None):
        if not self.current_query:
            return
        q = self.current_query
        if not query:
            b = q.textview.get_buffer()
            text = b.get_text(b.get_start_iter(), b.get_end_iter())
        else:
            text = query

        self.current_host = host = q.current_host
        if not host:
            dialogs.show_message(
                "error executing this query!",
                "could not execute query, because there is no selected host!"
            )
            return

        self.current_db = q.current_db
        if q.current_db:
            host.select_database(q.current_db)
        elif host.current_db:
            if not dialogs.confirm(
                    "query without selected db",
                    """warning: this query tab has no database selected
                    but the host-connection already has the database '%s' selected.
                    the author knows no way to deselect this database.
                    do you want to continue?""" % host.current_db.name, self.mainwindow):
                return

        update = False
        select = False
        q.editable = False
        # single popup
        q.add_record.set_sensitive(False)
        q.delete_record.set_sensitive(False)
        # per query buttons
        q.add_record.set_sensitive(False)
        q.delete_record.set_sensitive(False)
        q.apply_record.set_sensitive(False)
        q.local_search.set_sensitive(False)
        q.remove_order.set_sensitive(False)
        q.save_result.set_sensitive(False)
        q.save_result_sql.set_sensitive(False)

        affected_rows = 0
        last_insert_id = 0
        num_rows = 0
        num_fields = 0

        query_time = 0
        download_time = 0
        display_time = 0
        query_count = 0
        total_start = time.time()

        # cleanup last query model and treeview
        for col in q.treeview.get_columns():
            q.treeview.remove_column(col)
        if q.model:
            q.model.clear()

        _start = 0
        while _start < len(text):
            query_start = _start
            # search query end
            query_start, end = self.read_query(text, _start)
            if query_start is None:
                break
            thisquery = text[query_start:end]
            print "about to execute query %r" % thisquery
            _start = end + 1

            thisquery.strip(" \r\n\t;")
            if not thisquery:
                continue  # empty query
            query_count += 1
            query_hint = re.sub("[\n\r\t ]+", " ", thisquery[:40])
            q.label.set_text("executing query %d %s..." % (query_count, query_hint))
            q.label.window.process_updates(False)

            appendable = False
            appendable_result = self.is_query_appendable(thisquery)
            if appendable_result:
                appendable = True
                q.editable = self.is_query_editable(thisquery, appendable_result)
            print "appendable: %s, editable: %s" % (appendable, q.editable)

            ret = host.query(thisquery, encoding=q.encoding)
            query_time += host.query_time

            # if stop on error is enabled
            if not ret:
                print "mysql error: %r" % (host.last_error, )
                message = "error at: %s" % host.last_error.replace(
                    "You have an error in your SQL syntax.  "
                    "Check the manual that corresponds to your MySQL server version for the right syntax to use near ",
                    "")
                message = "error at: %s" % message.replace("You have an error in your SQL syntax; "
                                                           "check the manual that corresponds to your MySQL server "
                                                           "version for the right syntax to use near ", "")

                line_pos = 0
                pos = message.find("at line ")
                if pos != -1:
                    line_no = int(message[pos + 8:])
                    while 1:
                        line_no -= 1
                        if line_no < 1:
                            break
                        p = thisquery.find("\n", line_pos)
                        if p == -1:
                            break
                        line_pos = p + 1

                i = q.textview.get_buffer().get_iter_at_offset(query_start + line_pos)

                match = re.search("error at: '(.*)'", message, re.DOTALL)
                if match and match.group(1):
                    # set focus and cursor!
                    #print "search for ->%s<-" % match.group(1)
                    pos = text.find(match.group(1), query_start + line_pos, query_start + len(thisquery))
                    if not pos == -1:
                        i.set_offset(pos)
                else:
                    match = re.match("Unknown column '(.*?')", message)
                    if match:
                        # set focus and cursor!
                        pos = thisquery.find(match.group(1))
                        if not pos == 1:
                            i.set_offset(query_start + pos)

                q.textview.get_buffer().place_cursor(i)
                q.textview.scroll_to_iter(i, 0.0)
                q.textview.grab_focus()
                q.label.set_text(re.sub("[\r\n\t ]+", " ", message))
                return

            field_count = host.handle.field_count()
            if field_count == 0:
                # query without result
                update = True
                affected_rows += host.handle.affected_rows()
                last_insert_id = host.handle.insert_id()
                continue

            # query with result
            q.append_iter = None
            q.local_search.set_sensitive(True)
            q.add_record.set_sensitive(appendable)
            q.delete_record.set_sensitive(q.editable)
            select = True
            q.last_source = thisquery
            # get sort order!
            sortable = True  # todo
            current_order = self.get_order_from_query(thisquery)
            sens = False
            if len(current_order) > 0:
                sens = True
            q.remove_order.set_sensitive(sens and sortable)

            sort_fields = dict()
            for c, o in current_order:
                sort_fields[c.lower()] = o
            q.label.set_text("downloading resultset...")
            q.label.window.process_updates(False)

            start_download = time.time()
            result = host.handle.store_result()
            download_time = time.time() - start_download
            if download_time < 0:
                download_time = 0

            q.label.set_text("displaying resultset...")
            q.label.window.process_updates(False)

            # store field info
            q.result_info = result.describe()
            num_rows = result.num_rows()

            for col in q.treeview.get_columns():
                q.treeview.remove_column(col)

            columns = [gobject.TYPE_STRING] * field_count
            q.model = gtk.ListStore(*columns)
            q.treeview.set_model(q.model)
            q.treeview.set_rules_hint(True)
            q.treeview.set_headers_clickable(True)
            for i in range(field_count):
                title = q.result_info[i][0].replace("_", "__").replace("[\r\n\t ]+", " ")
                text_renderer = gtk.CellRendererText()
                if q.editable:
                    text_renderer.set_property("editable", True)
                    text_renderer.connect("edited", self.on_query_change_data, i)
                l = q.treeview.insert_column_with_data_func(-1, title, text_renderer, self.render_mysql_string, i)

                col = q.treeview.get_column(l - 1)

                if self.config.get_bool("result_view_column_resizable"):
                    col.set_resizable(True)
                else:
                    col.set_resizable(False)
                    col.set_min_width(int(self.config.get("result_view_column_width_min")))
                    col.set_max_width(int(self.config.get("result_view_column_width_max")))

                if sortable:
                    col.set_clickable(True)
                    col.connect("clicked", self.on_query_column_sort, i)
                    # set sort indicator
                    field_name = q.result_info[i][0].lower()
                    try:
                        sort_col = sort_fields[field_name]
                        col.set_sort_indicator(True)
                        if sort_col:
                            col.set_sort_order(gtk.SORT_ASCENDING)
                        else:
                            col.set_sort_order(gtk.SORT_DESCENDING)
                    except:
                        col.set_sort_indicator(False)
                else:
                    col.set_clickable(False)
                    col.set_sort_indicator(False)

            cnt = 0
            start_display = time.time()
            last_display = start_display
            for row in result.fetch_row(0):
                def to_string(f):
                    if type(f) == str:
                        f = f.decode(q.encoding, "replace")
                    elif f is None:
                        pass
                    else:
                        f = str(f)
                    return f
                q.model.append(map(to_string, row))
                cnt += 1
                if not cnt % 100 == 0:
                    continue

                now = time.time()
                if (now - last_display) < 0.2:
                    continue

                q.label.set_text("displayed %d rows..." % cnt)
                q.label.window.process_updates(False)
                last_display = now

            display_time = time.time() - start_display
            if display_time < 0:
                display_time = 0

        result = []
        if select:
            # there was a query with a result
            result.append("rows: %d" % num_rows)
            result.append("fields: %d" % field_count)
            q.save_result.set_sensitive(True)
            q.save_result_sql.set_sensitive(True)
        if update:
            # there was a query without a result
            result.append("affected rows: %d" % affected_rows)
            result.append("insert_id: %d" % last_insert_id)
        total_time = time.time() - total_start
        result.append("| total time: %.2fs (query: %.2fs" % (total_time, query_time))
        if select:
            result.append("download: %.2fs display: %.2fs" % (download_time, display_time))
        result.append(")")

        q.label.set_text(' '.join(result))
        self.blob_view.tv.set_editable(q.editable)
        self.blob_view.blob_update.set_sensitive(q.editable)
        self.blob_view.blob_load.set_sensitive(q.editable)
        # todo update_buttons()
        gc.collect()
        return True

    def assign_once(self, name, creator, *args):
        try:
            return self.created_once[name]
        except:
            obj = creator(*args)
            self.created_once[name] = obj
            return obj

    def on_save_query_clicked(self, button):
        if not self.current_query:
            return

        d = self.assign_once(
            "save dialog",
            gtk.FileChooserDialog, "save query", self.mainwindow, gtk.FILE_CHOOSER_ACTION_SAVE,
            (gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_SAVE, gtk.RESPONSE_ACCEPT))

        d.set_default_response(gtk.RESPONSE_ACCEPT)
        answer = d.run()
        d.hide()
        if not answer == gtk.RESPONSE_ACCEPT:
            return
        filename = d.get_filename()
        if os.path.exists(filename):
            if not os.path.isfile(filename):
                dialogs.show_message("save query", "%s already exists and is not a file!" % filename)
                return
            if not dialogs.confirm(
                    "overwrite file?",
                    "%s already exists! do you want to overwrite it?" % filename, self.mainwindow):
                return
        b = self.current_query.textview.get_buffer()
        query_text = b.get_text(b.get_start_iter(), b.get_end_iter())
        try:
            fp = file(filename, "wb")
            fp.write(query_text)
            fp.close()
        except:
            dialogs.show_message("save query", "error writing query to file %s: %s" % (filename, sys.exc_value))

    def on_load_query_clicked(self, button):
        if not self.current_query:
            return

        d = self.assign_once(
            "load dialog",
            gtk.FileChooserDialog, "load query", self.mainwindow, gtk.FILE_CHOOSER_ACTION_OPEN,
            (gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_OPEN, gtk.RESPONSE_ACCEPT))

        d.set_default_response(gtk.RESPONSE_ACCEPT)
        answer = d.run()
        d.hide()
        if not answer == gtk.RESPONSE_ACCEPT:
            return

        filename = d.get_filename()
        try:
            sbuf = os.stat(filename)
        except:
            dialogs.show_message("load query", "%s does not exists!" % filename)
            return
        if not S_ISREG(sbuf.st_mode):
            dialogs.show_message("load query", "%s exists, but is not a file!" % filename)
            return

        size = sbuf.st_size
        _max = int(self.config.get("ask_execute_query_from_disk_min_size"))
        if size > _max:
            if dialogs.confirm("load query", """
<b>%s</b> is very big (<b>%.2fMB</b>)!
opening it in the normal query-view may need a very long time!
if you just want to execute this skript file without editing and
syntax-highlighting, i can open this file using the <b>execute file from disk</b> function.
<b>shall i do this?</b>""" % (filename, size / 1024.0 / 1000.0), self.mainwindow):
                self.on_execute_query_from_disk_activate(None, filename)
                return
        try:
            fp = file(filename, "rb")
            query_text = fp.read()
            fp.close()
        except:
            dialogs.show_message("save query", "error writing query to file %s: %s" % (filename, sys.exc_value))
            return
        self.current_query.textview.get_buffer().set_text(query_text)

    def on_save_workspace_activate(self, button):
        d = self.assign_once(
            "save workspace dialog",
            gtk.FileChooserDialog, "save workspace", self.mainwindow, gtk.FILE_CHOOSER_ACTION_SAVE,
            (gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_SAVE, gtk.RESPONSE_ACCEPT))

        d.set_default_response(gtk.RESPONSE_ACCEPT)
        answer = d.run()
        d.hide()
        if not answer == gtk.RESPONSE_ACCEPT:
            return
        filename = d.get_filename()
        if os.path.exists(filename):
            if not os.path.isfile(filename):
                dialogs.show_message("save workspace", "%s already exists and is not a file!" % filename)
                return
            if not dialogs.confirm(
                    "overwrite file?",
                    "%s already exists! do you want to overwrite it?" % filename, self.mainwindow):
                return
        try:
            fp = file(filename, "wb")
            pickle.dump(self, fp)
            fp.close()
        except:
            dialogs.show_message(
                "save workspace",
                "error writing workspace to file %s: %s/%s" % (filename, sys.exc_type, sys.exc_value))

    def on_restore_workspace_activate(self, button):
        global new_instance
        d = self.assign_once(
            "restore workspace dialog",
            gtk.FileChooserDialog, "restore workspace", self.mainwindow, gtk.FILE_CHOOSER_ACTION_OPEN,
            (gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_OPEN, gtk.RESPONSE_ACCEPT))

        d.set_default_response(gtk.RESPONSE_ACCEPT)
        answer = d.run()
        d.hide()
        if not answer == gtk.RESPONSE_ACCEPT:
            return
        filename = d.get_filename()
        if not os.path.exists(filename):
            dialogs.show_message("restore workspace", "%s does not exists!" % filename)
            return
        if not os.path.isfile(filename):
            dialogs.show_message("restore workspace", "%s exists, but is not a file!" % filename)
            return

        try:
            fp = file(filename, "rb")
            print "i am unpickling:", self
            new_instance = pickle.load(fp)
            print "got new instance:", new_instance
            fp.close()
        except:
            dialogs.show_message(
                "restore workspace",
                "error restoring workspace from file %s: %s/%s" % (filename, sys.exc_type, sys.exc_value))
        self.mainwindow.destroy()

    # def __setstate__(self, state):
    #     self.state = state

    def on_query_font_clicked(self, button):
        d = self.assign_once("query text font", gtk.FontSelectionDialog, "select query font")
        d.set_font_name(self.config.get("query_text_font"))
        answer = d.run()
        d.hide()
        if not answer == gtk.RESPONSE_OK:
            return
        font_name = d.get_font_name()
        self.current_query.set_query_font(font_name)
        self.config.config["query_text_font"] = font_name
        self.config.save()

    def on_newquery_button_clicked(self, button):
        self.add_query_tab(QueryTab(self.query_notebook, self))

    def on_query_notebook_switch_page(self, nb, pointer, page):
        if page >= len(self.queries):
            page = len(self.queries) - 1
        q = self.current_query = self.queries[page]
        q.on_query_db_eventbox_button_press_event(None, None)
        self.query_changed(q)

    def query_changed(self, q):
        for f in self.query_changed_listener:
            try:
                f(q)
            except:
                print "query_change_listener %r had exception" % f

    def on_closequery_button_clicked(self, button):
        if len(self.queries) == 1:
            return
        self.current_query.destroy()
        self.del_query_tab(self.current_query)
        self.query_notebook.remove_page(self.query_notebook.get_current_page())
        gc.collect()

    def on_rename_query_tab_clicked(self, button):
        label = self.current_query.get_label()
        new_name = dialogs.input_dialog("Rename tab", "Please enter the new name of this tab:",
                                        label.get_text(),
                                        self.mainwindow)
        if new_name is None:
            return
        if new_name == "":
            self.current_query.last_auto_name = None
            self.current_query.update_db_label()
            return
        self.current_query.user_rename(new_name)

    def on_fc_reset_clicked(self, button):
        for i in range(self.fc_count):
            self.fc_entry[i].set_text("")
            if i == 0:
                self.fc_combobox[i].set_active(0)
                self.fc_op_combobox[i].set_active(0)
            else:
                self.fc_combobox[i].set_active(-1)
                self.fc_op_combobox[i].set_active(-1)
            if i:
                self.fc_logic_combobox[i - 1].set_active(0)

    def on_quit_activate(self, item):
        gtk.main_quit()

    def on_about_activate(self, item):
        self.about_dialog.run()
        self.about_dialog.hide()
        # aboutdialog = self.xml.get_widget("aboutdialog")
        # aboutdialog.set_version(version)
        # aboutdialog.run()
        # aboutdialog.hide()

    def on_changelog_activate(self, item):
        self.changelog_dialog.show()

    def on_nb_change_page(self, np, pointer, page):
        if page == 2:
            self.tableslist.redraw()
            return
        path, column = self.connections_tv.get_cursor()
        if not path:
            return
        if len(path) == 3 and page == 3:
            self.table_view.update(path)

    def on_mainwindow_key_press_event(self, _window, event):
        if event.keyval == keysyms.Control_L:
            self.left_control_key_is_pressed = True

    def on_mainwindow_key_release_event(self, _window, event):
        if event.keyval == keysyms.F3:
            self.current_query.local_search_action.on_local_search_button_clicked(None, True)
            return True
        if event.keyval == keysyms.m and self.left_control_key_is_pressed:
            self.message_notebook.set_visible(not self.message_notebook.get_visible())
            return True
        if event.keyval == keysyms.h and self.left_control_key_is_pressed:
            self.connections_tv_container.set_visible(not self.connections_tv_container.get_visible())
            return True
        if event.keyval == keysyms.Control_L:
            self.left_control_key_is_pressed = False
            return True

    def get_current_table(self):
        path, column = self.connections_tv.get_cursor()
        _iter = self.connections_tv.connections_model.get_iter(path)
        return path, column, _iter, self.connections_tv.connections_model.get_value(_iter, 0)

    def get_db_iter(self, db):
        return self.get_connections_object_at_depth(db, 1)

    def get_host_iter(self, host):
        return self.get_connections_object_at_depth(host, 0)

    def get_connections_object_at_depth(self, obj, depth):
        d = 0
        model = self.connections_tv.connections_model
        _iter = model.get_iter_first()
        while _iter:
            if d == depth and model.get_value(_iter, 0) == obj:
                return _iter
            if d < depth and model.iter_has_child(_iter):
                _iter = model.iter_children(_iter)
                d += 1
                continue
            new_iter = model.iter_next(_iter)
            if not new_iter:
                _iter = model.iter_parent(_iter)
                d -= 1
                _iter = model.iter_next(_iter)
            else:
                _iter = new_iter
        return None

    def on_execution_timeout(self, button):
        value = button.get_value()
        if value < 0.1:
            self.execution_timer_running = False
            return False
        if not self.on_execute_query_clicked():
            # stop on error
            button.set_value(0)
            value = 0
        if value != self.execution_timer_interval:
            self.execution_timer_running = False
            self.on_reexecution_spin_changed(button)
            return False
        return True

    def on_reexecution_spin_changed(self, button):
        value = button.get_value()
        if self.execution_timer_running:
            return
        self.execution_timer_running = True
        self.execution_timer_interval = value
        gobject.timeout_add(int(value * 1000), self.on_execution_timeout, button)

    def on_query_popup(self, item):
        q = self.current_query
        path, column = q.treeview.get_cursor()
        _iter = q.model.get_iter(path)

        if item.name == "copy_field_value":
            col_max = q.model.get_n_columns()
            for col_num in range(col_max):
                if column == q.treeview.get_column(col_num):
                    break
            else:
                print "column not found!"
                return
            value = q.model.get_value(_iter, col_num)
            self.clipboard.set_text(value)
            self.pri_clipboard.set_text(value)
        elif item.name == "copy_record_as_csv":
            col_max = q.model.get_n_columns()
            value = ""
            for col_num in range(col_max):
                if value:
                    value += self.config.get("copy_record_as_csv_delim")
                v = q.model.get_value(_iter, col_num)
                if not v is None:
                    value += v
            self.clipboard.set_text(value)
            self.pri_clipboard.set_text(value)
        elif item.name == "copy_record_as_quoted_csv":
            col_max = q.model.get_n_columns()
            value = ""
            for col_num in range(col_max):
                if value:
                    value += self.config.get("copy_record_as_csv_delim")
                v = q.model.get_value(_iter, col_num)
                if not v is None:
                    v = v.replace("\"", "\\\"")
                    value += '"%s"' % v
            self.clipboard.set_text(value)
            self.pri_clipboard.set_text(value)
        elif item.name == "copy_column_as_csv":
            col_max = q.model.get_n_columns()
            for col_num in range(col_max):
                if column == q.treeview.get_column(col_num):
                    break
            else:
                print "column not found!"
                return
            value = ""
            _iter = q.model.get_iter_first()
            while _iter:
                if value:
                    value += self.config.get("copy_record_as_csv_delim")
                v = q.model.get_value(_iter, col_num)
                if not v is None:
                    value += v
                _iter = q.model.iter_next(_iter)
            self.clipboard.set_text(value)
            self.pri_clipboard.set_text(value)
        elif item.name == "copy_column_as_quoted_csv":
            col_max = q.model.get_n_columns()
            for col_num in range(col_max):
                if column == q.treeview.get_column(col_num):
                    break
            else:
                print "column not found!"
                return
            value = ""
            _iter = q.model.get_iter_first()
            while _iter:
                if value:
                    value += self.config.get("copy_record_as_csv_delim")
                v = q.model.get_value(_iter, col_num)
                if not v is None:
                    v = v.replace("\"", "\\\"")
                    value += '"%s"' % v
                _iter = q.model.iter_next(_iter)
            self.clipboard.set_text(value)
            self.pri_clipboard.set_text(value)
        elif item.name == "copy_column_names":
            value = ""
            for col in q.treeview.get_columns():
                if value:
                    value += self.config.get("copy_record_as_csv_delim")
                value += col.get_title().replace("__", "_")
            self.clipboard.set_text(value)
            self.pri_clipboard.set_text(value)
        elif item.name == "set_value_null":
            col_max = q.model.get_n_columns()
            for col_num in range(col_max):
                if column == q.treeview.get_column(col_num):
                    break
            else:
                print "column not found!"
                return
            table, where, field, value, row_iter = self.get_unique_where(q.last_source, path, col_num)
            update_query = "update `%s` set `%s`=NULL where %s limit 1" % (table, field, where)
            if self.current_host.query(update_query, encoding=q.encoding):
                q.model.set_value(row_iter, col_num, None)
        elif item.name == "set_value_now":
            col_max = q.model.get_n_columns()
            for col_num in range(col_max):
                if column == q.treeview.get_column(col_num):
                    break
            else:
                print "column not found!"
                return
            table, where, field, value, row_iter = self.get_unique_where(q.last_source, path, col_num)
            update_query = "update `%s` set `%s`=now() where %s limit 1" % (table, field, where)
            if not self.current_host.query(update_query, encoding=q.encoding):
                return
            self.current_host.query("select `%s` from `%s` where %s limit 1" % (field, table, where))
            result = self.current_host.handle.store_result().fetch_row(0)
            if len(result) < 1:
                print "error: can't find modfied row!?"
                return
            q.model.set_value(row_iter, col_num, result[0][0])
        elif item.name == "set_value_unix_timestamp":
            col_max = q.model.get_n_columns()
            for col_num in range(col_max):
                if column == q.treeview.get_column(col_num):
                    break
            else:
                print "column not found!"
                return
            table, where, field, value, row_iter = self.get_unique_where(q.last_source, path, col_num)
            update_query = "update `%s` set `%s`=unix_timestamp(now()) where %s limit 1" % (table, field, where)
            if not self.current_host.query(update_query, encoding=q.encoding):
                return
            self.current_host.query("select `%s` from `%s` where %s limit 1" % (field, table, where))
            result = self.current_host.handle.store_result().fetch_row(0)
            if len(result) < 1:
                print "error: can't find modfied row!?"
                return
            q.model.set_value(row_iter, col_num, result[0][0])
        elif item.name == "set_value_as_password":
            col_max = q.model.get_n_columns()
            for col_num in range(col_max):
                if column == q.treeview.get_column(col_num):
                    break
            else:
                print "column not found!"
                return
            table, where, field, value, row_iter = self.get_unique_where(q.last_source, path, col_num)
            update_query = "update `%s` set `%s`=password('%s') where %s limit 1" % (table, field,
                                                                                     self.current_host.escape(value),
                                                                                     where)
            if not self.current_host.query(update_query, encoding=q.encoding):
                return
            self.current_host.query("select `%s` from `%s` where %s limit 1" % (field, table, where))
            result = self.current_host.handle.store_result().fetch_row(0)
            if len(result) < 1:
                print "error: can't find modfied row!?"
                return
            q.model.set_value(row_iter, col_num, result[0][0])
        elif item.name == "set_value_to_sha":
            col_max = q.model.get_n_columns()
            for col_num in range(col_max):
                if column == q.treeview.get_column(col_num):
                    break
            else:
                print "column not found!"
                return
            table, where, field, value, row_iter = self.get_unique_where(q.last_source, path, col_num)
            update_query = "update `%s` set `%s`=sha1('%s') where %s limit 1" % (table, field,
                                                                                 self.current_host.escape(value),
                                                                                 where)
            if not self.current_host.query(update_query, encoding=q.encoding):
                return
            self.current_host.query("select `%s` from `%s` where %s limit 1" % (field, table, where))
            result = self.current_host.handle.store_result().fetch_row(0)
            if len(result) < 1:
                print "error: can't find modfied row!?"
                return
            q.model.set_value(row_iter, col_num, result[0][0])

    def on_template(self, button, t):
        current_table = self.get_selected_table()
        current_fc_table = current_table

        if t.find("$table$") != -1:
            if not current_table:
                dialogs.show_message(
                    "info",
                    "no table selected!\nyou can't execute a template with $table$ in it, "
                    "if you have no table selected!")
                return
            t = t.replace("$table$", self.current_host.escape_table(current_table.name))

        pos = t.find("$primary_key$")
        if pos != -1:
            if not current_table:
                dialogs.show_message(
                    "info",
                    "no table selected!\nyou can't execute a template with $primary_key$ in it, "
                    "if you have no table selected!")
                return
            if not current_table.fields:
                dialogs.show_message(
                    "info",
                    "sorry, can't execute this template, because table '%s' has no fields!" % current_table.name)
                return
            # is the next token desc or asc?
            result = re.search("(?i)[ \t\r\n]*(de|a)sc", t[pos:])
            order_dir = ""
            if result:
                o = result.group(1).lower()
                if o == "a":
                    order_dir = "asc"
                else:
                    order_dir = "desc"

            replace = ""
            while 1:
                primary_key = ""
                for name in current_table.field_order:
                    props = current_table.fields[name]
                    if props[3] != "PRI":
                        continue
                    if primary_key:
                        primary_key += " " + order_dir + ", "
                    primary_key += self.current_host.escape_field(name)
                if primary_key:
                    replace = primary_key
                    break
                key = ""
                for name in current_table.field_order:
                    props = current_table.fields[name]
                    if props[3] != "UNI":
                        continue
                    if key:
                        key += " " + order_dir + ", "
                    key += self.current_host.escape_field(name)
                if key:
                    replace = key
                    break
                replace = self.current_host.escape_field(current_table.field_order[0])
                break
            t = t.replace("$primary_key$", replace)

        if t.find("$field_conditions$") != -1:
            if not self.field_conditions_initialized:
                self.field_conditions_initialized = True
                self.fc_count = 4
                self.fc_window = self.xml.get_widget("field_conditions")
                table = self.xml.get_widget("fc_table")
                table.resize(1 + self.fc_count, 4)
                self.fc_entry = []
                self.fc_combobox = []
                self.fc_op_combobox = []
                self.fc_logic_combobox = []
                for i in range(self.fc_count):
                    self.fc_entry.append(gtk.Entry())
                    self.fc_entry[i].connect("activate", lambda *e: self.fc_window.response(gtk.RESPONSE_OK))
                    self.fc_combobox.append(gtk.combo_box_new_text())
                    self.fc_op_combobox.append(gtk.combo_box_new_text())
                    self.fc_op_combobox[i].append_text("=")
                    self.fc_op_combobox[i].append_text("<")
                    self.fc_op_combobox[i].append_text(">")
                    self.fc_op_combobox[i].append_text("!=")
                    self.fc_op_combobox[i].append_text("LIKE")
                    self.fc_op_combobox[i].append_text("NOT LIKE")
                    self.fc_op_combobox[i].append_text("ISNULL")
                    self.fc_op_combobox[i].append_text("NOT ISNULL")
                    if i:
                        self.fc_logic_combobox.append(gtk.combo_box_new_text())
                        self.fc_logic_combobox[i - 1].append_text("disabled")
                        self.fc_logic_combobox[i - 1].append_text("AND")
                        self.fc_logic_combobox[i - 1].append_text("OR")
                        table.attach(self.fc_logic_combobox[i - 1], 0, 1, i + 1, i + 2)
                        self.fc_logic_combobox[i - 1].show()
                    table.attach(self.fc_combobox[i], 1, 2, i + 1, i + 2)
                    table.attach(self.fc_op_combobox[i], 2, 3, i + 1, i + 2)
                    table.attach(self.fc_entry[i], 3, 4, i + 1, i + 2)
                    self.fc_combobox[i].show()
                    self.fc_op_combobox[i].show()
                    self.fc_entry[i].show()
            if not current_table:
                dialogs.show_message(
                    "info",
                    "no table selected!\nyou can't execute a template with "
                    "$field_conditions$ in it, if you have no table selected!")
                return

            last_field = []
            for i in range(self.fc_count):
                last_field.append(self.fc_combobox[i].get_active_text())
                self.fc_combobox[i].get_model().clear()
                if i:
                    self.fc_logic_combobox[i - 1].set_active(0)
            fc = 0
            for field_name in current_table.field_order:
                for k in range(self.fc_count):
                    self.fc_combobox[k].append_text(field_name)
                    if last_field[k] == field_name:
                        self.fc_combobox[k].set_active(fc)
                fc += 1
            if not self.fc_op_combobox[0].get_active_text():
                self.fc_op_combobox[0].set_active(0)
            if not self.fc_combobox[0].get_active_text():
                self.fc_combobox[0].set_active(0)

            answer = self.fc_window.run()
            self.fc_window.hide()
            if answer != gtk.RESPONSE_OK:
                return

            def field_operator_value(field, op, value):
                if op == "ISNULL":
                    return "isnull(`%s`)" % field
                if op == "NOT ISNULL":
                    return "not isnull(`%s`)" % field
                eval_kw = "eval: "
                if value.startswith(eval_kw):
                    return "`%s` %s %s" % (field, op, value[len(eval_kw):])
                return "%s %s '%s'" % (self.current_host.escape_field(field), op, self.current_host.escape(value))

            conditions = "%s" % (
                field_operator_value(
                    self.fc_combobox[0].get_active_text(),
                    self.fc_op_combobox[0].get_active_text(),
                    self.fc_entry[0].get_text()
                )
            )
            for i in range(1, self.fc_count):
                if self.fc_logic_combobox[i - 1].get_active_text() == "disabled" \
                        or self.fc_combobox[i].get_active_text() == "" \
                        or self.fc_op_combobox[i].get_active_text() == "":
                    continue
                conditions += " %s %s" % (
                    self.fc_logic_combobox[i - 1].get_active_text(),
                    field_operator_value(
                        self.fc_combobox[i].get_active_text(),
                        self.fc_op_combobox[i].get_active_text(),
                        self.fc_entry[i].get_text()
                    )
                )
            t = t.replace("$field_conditions$", conditions)

        try:
            new_order = self.stored_orders[self.current_host.current_db.name][current_table.name]
            print "found stored order: %r" % (new_order, )
            query = t
            try:
                r = self.query_order_re
            except:
                r = self.query_order_re = re.compile(re_src_query_order)
            match = re.search(r, query)
            if match:
                before, order, after = match.groups()
                order = ""
                addition = ""
            else:
                match = re.search(re_src_after_order, query)
                if not match:
                    before = query
                    after = ""
                else:
                    before = query[0:match.start()]
                    after = match.group()
                addition = "\norder by\n\t"
            order = ""
            for col, o in new_order:
                if order:
                    order += ",\n\t"
                order += self.current_host.escape_field(col)
                if not o:
                    order += " desc"
            if order:
                new_query = ''.join([before, addition, order, after])
            else:
                new_query = re.sub("(?i)order[ \r\n\t]+by[ \r\n\t]+", "", before + after)

            t = new_query
        except:
            pass
        self.on_execute_query_clicked(None, t)

    def render_mysql_string(self, column, cell, model, _iter, _id):
        o = model.get_value(_iter, _id)
        if not o is None:
            cell.set_property("background", None)
            if len(o) < 256:
                cell.set_property("text", o)
                cell.set_property("editable", True)
            else:
                cell.set_property("text", o[0:256] + "...")
                cell.set_property("editable", False)
        else:
            cell.set_property("background", self.config.get("null_color"))
            cell.set_property("text", "")
            cell.set_property("editable", True)

    def on_reread_config_activate(self, item):
        self.config.load()

    def on_query_encoding_changed(self, menuitem, data):
        self.current_query.set_query_encoding(data[0])

    def process_events(self):
        while gtk.events_pending():
            gtk.main_iteration(False)

    def get_selected_table(self):
        path, column = self.connections_tv.get_cursor()
        depth = len(path)
        _iter = self.connections_tv.connections_model.get_iter(path)
        if depth == 3:
            return self.connections_tv.connections_model.get_value(_iter, 0)
        return None

    def read_expression(self, query, _start=0, concat=True, update_function=None, update_offset=0, icount=0):
        ## TODO!
        # r'(?is)("(?:[^\\]|\\.)*?")|(\'(?:[^\\]|\\.)*?\')|(`(?:[^\\]|\\.)*?`)|([^ \r\n\t]*[ \r\n\t]*\()|(\))|([0-9]+(?:\\.[0-9]*)?)|([^ \r\n\t,()"\'`]+)|(,)')
        try:
            r = self.query_expr_re
        except:
            r = self.query_expr_re = query_regular_expression

        # print "read expr in", query
        match = r.search(query, _start)
        #if match: print match.groups()
        if not match:
            return None, None
        for i in range(1, match.lastindex + 1):
            if match.group(i):
                t = match.group(i)
                e = match.end(i)
                current_token = t
                if current_token[len(current_token) - 1] == "(":
                    while 1:
                        icount += 1
                        if update_function is not None and icount >= 10:
                            icount = 0
                            update_function(False, update_offset + e)
                        #print "at", [query[e:e+15]], "..."
                        exp, end = self.read_expression(query, e, False, update_function, update_offset, icount)
                        #print "got inner exp:", [exp]
                        if not exp:
                            break
                        e = end
                        if concat:
                            t += " " + exp
                        if exp == ")":
                            break

                return t, e
        print "should not happen!"
        return None, None

