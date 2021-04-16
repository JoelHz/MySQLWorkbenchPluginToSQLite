# -*- coding: utf-8 -*-
# MySQL Workbench module
# conversor de MySQL a SQLite
# Written in MySQL Workbench 8.0.22

import re
import StringIO

import grt
import mforms

from grt.modules import Workbench
from wb import DefineModule, wbinputs
from workbench.ui import WizardForm, WizardPage
from mforms import newButton, newCodeEditor, FileChooser

ModuleInfo = DefineModule(name='ToSQLite',author='Jose Uzcategui',version='1.0' )

@ModuleInfo.plugin('wb.util.ToSQLite',
                   caption='To SQLite',
                   input=[wbinputs.currentCatalog()],
                   groups=['Catalog/Utilities', 'Menu/Catalog'])

@ModuleInfo.export(grt.INT, grt.classes.db_Catalog)

def exportSQLite(cat):
    #------------------------------------------------------------------------
    # format header author, dates, version, etc
    def info_format(header, body):
        verbody = lineFormat(body)
        retString = ''
        if verbody == '':
            retString = ''
        elif '\n' in verbody:
            # Multiline comment
            retString = '-- %s:\n--   %s\n' % (header, re.sub(r'\n', '\n--   ', verbody))
        else:
            # Single line
             retString = '-- %-14s %s\n' % (header + ':', verbody)
        return retString
    #------------------------------------------------------------------------
    # form sql sentences 
    def composeSenten(txt,dbItm):
        insrtStm = []
        viewsStm = []
        listschm = []
        erroschm = []
        for schema in dbItm.schemata:
            txt.write('-- Schema : %s \n' % (schema.name))
            listschm.append(schema.name)
            erroschm = verifyDBObjec(schema.name, listschm)
            alertsMessage('schema '+ schema.name,erroschm,txt)
            txt.write(commentFormat(schema.comment))
            viewsStm += create_views(schema)
            liststbl = []
            errostbl = []
            checkRefCir(schema,txt)
            for table in schema.tables:
                txt.write('\n-- Table definition : %s \n' % (table.name))
                liststbl.append(table.name)
                errostbl = verifyDBObjec(table.name, liststbl)
                alertsMessage('table '+table.name,errostbl,txt)
                if lineFormat(table.comment):
                    txt.write(commentFormat(lineFormat(table.comment)))
                insrtStm += export_inserts(table,schema.name)
                createTable(table,txt)
                    
        if not listschm:
            txt.write('There is no schem(s)/table(s)/index(es) to format')
        return tuple((viewsStm,insrtStm))
    #------------------------------------------------------------------------
    # verify wether name is duplicated or missing
    def verifyDBObjec(elemnt, list):
        resp = []
        if not elemnt:
            resp.append('missing name')      
        if list.count(elemnt) > 1:
            resp.append('duplicate name')
        return resp
    #------------------------------------------------------------------------
    # alert error(s) found on database conversion
    def alertsMessage(typelmt,messages,txt):
        if messages:
            errortxt = '\n-- Alert : %s with error(s) : \n' % (typelmt)
            for err in messages:
                    errortxt =  errortxt + '\t\t-- ' + err + '\n'
            txt.write(errortxt)
    #------------------------------------------------------------------------
    # check for cicular reference
    def checkRefCir(sch,txt):
        # array (list) with tuple with the name of a main table and a list of its referenced table  :
        # [(MainTable1, [Referenced1toMainTable1,...,ReferencedNtoMainTable1],(MainTable2, [Referenced1toMainTable2,...,ReferencedNtoMainTable2]),...]
        listA =  [(table.name,map(lambda x: x.referencedTable.name, table.foreignKeys)) for table in sch.tables]
        # detect when a main table is referenced and that referenced table has a a reference with the main table
        listB = [a for a in [[y for y in listA if (y[0] in x[1]) and (x[0] in y[1])  ] for x in listA] if a]
        # list of lists (very deep) is created, time to flat if it exits
        reStr = flattener(listB)
        if reStr:
            errFound = ', '.join(set(reStr))
            txt.write('\n-- ALERT: Circular reference may be on tables %s: \n' % (errFound))

    #------------------------------------------------------------------------
    # function to flatten list
    def flattener(data):
        flat1 = [y for x in data for y in x] # remove the deepest list
        flat2 = [[y[0]]+y[1] for y in flat1] # create a 2D list inside list
        flat3 = [y for x in flat2 for y in x] # remove all list inside
        return flat3
    #------------------------------------------------------------------------
    # format comment
    def commentFormat(body):
        verbody = lineFormat(body)
        retString = ''
        if verbody == '':
            retString = ''
        elif '\n' in verbody:
            # Multiline comment
            retString = '\n--   %s' % re.sub(r'\n', '\n--   ', verbody)
        else:
            # Single line
            retString = '-- %s' % verbody
        return retString
    #------------------------------------------------------------------------
    # reformat string to remove empty lines with \n only 
    def lineFormat(strng):
        a = strng.strip()
        y = ''
        if a :
            n = strng.rstrip('\t').splitlines() 
            y = '\n'.join([x.strip() for x in n if x.strip()])
            if n == 1:
                y = y.rstrip('\n')
        return y
    #------------------------------------------------------------------------
    # from schema finds all view and fill a list with them, that list is returned to function 
    def create_views(schema):
        views = []
        for v in schema.views:
            viewdata = ('-- Definition of View %s :' % (extract_name(v.sqlDefinition)))
            views.append(viewdata)
            viewdata = ('DROP VIEW IF EXISTS %s;' % (extract_name(v.sqlDefinition)))
            views.append(viewdata)
            viewdata = ( '%s \n' % (re.sub(r'`', '', v.sqlDefinition)))
            views.append(viewdata)
            
        return views
    #------------------------------------------------------------------------
    # the name of the view is found out from sql definition property 
    def extract_name(sqldef):
        return re.search(r'`(.+)`',sqldef).group(1)
    #------------------------------------------------------------------------
    # function to create sentence table, triggers and save the inserts statemets/views, if any exists, in a list for later
    def createTable(table,txt):
        txt.write('\nDROP TABLE IF EXISTS %s;\n' % (table.name))
        txt.write('CREATE TABLE IF NOT EXISTS %s(\n' % (table.name))

        primary_key = [i for i in table.indices if i.isPrimary == 1]
        primary_key = primary_key[0] if len(primary_key) > 0 else None

        pk_column = None
        if primary_key and len(primary_key.columns) == 1:
            pk_column = primary_key.columns[0].referencedColumn

        col_comment = ''
        listscol = []
        for i, column in enumerate(table.columns):
            check, sqlite_type, flags = '', None, None
            listscol.append(column.name)
            erroscol = verifyDBObjec(column.name, listscol)
            if column.simpleType:
                sqlite_type = column.simpleType.name
                flags = column.simpleType.flags
            else:
                sqlite_type = column.userType.name
                flags = column.flags
            length = column.length
            # For INTEGER PRIMARY KEY column to become an alias for the rowid
            # the type needs to be "INTEGER" not "INT"
            # we fix it for other columns as well
            if 'INT' in sqlite_type or sqlite_type == 'LONG':
                sqlite_type = 'INTEGER'
                length = -1
                # Check flags for "unsigned"
                if 'UNSIGNED' in column.flags:
                    check = column.name + '>=0'
            # We even implement ENUM (because we can)
            if sqlite_type == 'ENUM':
                sqlite_type = 'TEXT'
                if column.datatypeExplicitParams:
                    check = (column.name + ' IN' +
                             column.datatypeExplicitParams)
            if i > 0:
                txt.write(',' + commentFormat(col_comment) + '\n')
                alertsMessage('column ' + column.name,erroscol,txt)
            txt.write('  ' + column.name)
            # Type is optional in SQLite
            if sqlite_type != '':
                txt.write(' ' + sqlite_type)

            # Must specify single-column PKs as column-constraints for AI/rowid
            # behaviour
            if column == pk_column:
                txt.write(' PRIMARY KEY')
                if primary_key.columns[0].descend == 1:
                    txt.write(' DESC')
                # Only PK columns can be AI in SQLite
                if column.autoIncrement == 1:
                    txt.write(' AUTOINCREMENT')
            # Check for NotNull
            if column.isNotNull == 1:
                txt.write(' NOT NULL')

            if check != '':
                txt.write(' CHECK(' + check + ')')

            if column.defaultValue != '':
                txt.write(' DEFAULT ' + column.defaultValue)

            col_comment = column.comment

        # For multicolumn PKs
        if primary_key and not pk_column:
            txt.write(',%s\n  PRIMARY KEY(%s)' % (
                      commentFormat(col_comment),
                      indx_cols(primary_key)))
            col_comment = ''
        listsind = []
        # Put non-primary, UNIQUE Keys in CREATE TABLE as well (because we can)
        for index in table.indices:
            listscol.append(index.name)
            errosind = verifyDBObjec(index.name, listscol)
            alertsMessage('index '+index.name,errosind,txt)
            if index != primary_key and index.indexType == 'UNIQUE':
                txt.write(',%s\n' % commentFormat(col_comment))
                col_comment = ''
                if index.name != '':
                    txt.write('  CONSTRAINT %s\n  ' % index.name)
                txt.write('  UNIQUE(%s)' % indx_cols(index))
        
        for fkey in table.foreignKeys:
            have_fkeys = 1
            txt.write(',%s\n' % commentFormat(col_comment))
            col_comment = ''
            if fkey.name != '':
                txt.write('  CONSTRAINT %s\n  ' % fkey.name)
            txt.write('  FOREIGN KEY(%s)\n' % fk_columns(fkey.columns))
            txt.write('    REFERENCES %s(%s)' % (
                      fkey.referencedTable.name,
                      fk_columns(fkey.referencedColumns)))
            if fkey.deleteRule in ['RESTRICT', 'CASCADE', 'SET NULL']:
                txt.write('\n    ON DELETE ' + fkey.deleteRule)
            if fkey.updateRule in ['RESTRICT', 'CASCADE', 'SET NULL']:
                txt.write('\n    ON UPDATE ' + fkey.updateRule)
            if is_deferred(fkey):
                txt.write(' DEFERRABLE INITIALLY DEFERRED')

        txt.write(commentFormat(col_comment) + '\n);\n')

        # CREATE INDEX statements for all non-primary, non-unique, non-foreign
        # indexes
        for i, index in enumerate(table.indices):
            if index.indexType == 'INDEX':
                #index_name = table.name + '.' + index.name
                index_name = index.name
                if index.name == '':
                    #index_name = table.name + '.index' + i
                    index_name = 'index' + i
                txt.write('CREATE INDEX %s ON %s (%s);\n' % (
                          index_name,
                          table.name,
                          indx_cols(index)))

        # Write the Triggers
        for trig in table.triggers:
            trigg = create_trigger(trig.sqlDefinition,trig.event,trig.timing,table.name,trig.name)
            txt.write(' %s ' % (trigg))
    #------------------------------------------------------------------------
    # Create trigger sentences 
    def create_trigger(charwrds,event,timing,tblname,tname):
        tbody = re.sub(r'\n', '‡', charwrds)
        ttag = ''
        if "WHEN" in tbody:
             begin_ind = tbody.index('WHEN')
             final_ind = tbody.index('BEGIN') - 3
             ttag = ' ' + tbody[begin_ind:final_ind]
        begin_ind = charwrds.index('BEGIN')
        tdeff = charwrds[begin_ind:]
        tdefi = ('\nCREATE TRIGGER %s ON %s \n %s ;\n' % (tname+' '+timing+' '+event,tblname + ttag,tdeff))
        return tdefi
    #------------------------------------------------------------------------
    # list of indexes, not array 
    def indx_cols(index):
        s = ''
        for i, column in enumerate(index.columns):
            if i > 0:
                s += ','
            s += column.referencedColumn.name
            if column.descend == 1:
                s += ' DESC'
        return s
    #------------------------------------------------------------------------
    # create sentence insert
    def export_inserts(tbl,sch):
        listins = []
        is_InsStmt = tbl.inserts().splitlines()
        if is_InsStmt :
            listins = ['-- Declare insert statments for table '+ tbl.name + ':\n']
        for insert in tbl.inserts().splitlines():
            del_single_quote = re.sub(r'`', '', insert)
            del_duoble_quote = re.sub(r'\\\'', '\'', del_single_quote)
            patternFind = ' ' + sch + '.'
            del_schema_name = re.sub(patternFind, ' ', del_duoble_quote)

            valInd = del_schema_name.index("VALUES (") + 8
            valCol = del_schema_name[valInd:].upper()
            litCol = valCol.split(',')
            allSentence = ''
            # add reserved words
            resrvW = ["DATETIME"]
            if any(x in valCol for x in resrvW):
                litCol1 = []
                for itm in litCol:
                    if any(x in itm for x in resrvW):
                        lastIndC = itm.rfind("'")
                        initIndC = itm.find("'") + 1
                        newItem = itm[initIndC:lastIndC]
                        litCol1.append(newItem)
                    else:
                        litCol1.append(itm)
                separator = ','
                allSentence = del_schema_name[:valInd]+separator.join(litCol1)
            else:
                separator = ','
                allSentence = del_schema_name[:valInd]+separator.join(litCol)
            listins.append(' %s \n' % (allSentence))
        return listins

    #------------------------------------------------------------------------
    # list of foreings keys, not array 
    def fk_columns(columns):
        s = ''
        for i, column in enumerate(columns):
            if i > 0:
                s += ','
            s += column.name
        return s
    #------------------------------------------------------------------------
    # Add views and inserts if any
    def addViewInst(list,txt):
        views = list[0]
        inser = list[1]
        
        if views:
            txt.write('\n')

        for v in views:
            txt.write('%s\n' % (v))

        if inser:
            txt.write('\nPRAGMA foreign_keys = ON;\n')

        for i in inser:
            txt.write('%s' % (i))
    #------------------------------------------------------------------------
    # coments to defer foreign key
    def is_deferred(fkey):
        # Hack: if comment starts with "Defer..." we make it a deferred FK could
        # use member 'deferability' (WB has it), but there is no GUI for it
        return fkey.comment.lstrip().lower()[0:5] == 'defer'
    #------------------------------------------------------------------------
    #Main function to convert MySQL to SQLite Format
    txt = StringIO.StringIO()
    txt.write(info_format(
            'Creator',
                'MySQL Workbench %d.%d.%d/ExportSQLite Plugin %s' % (
                    grt.root.wb.info.version.majorNumber,
                    grt.root.wb.info.version.minorNumber,
                    grt.root.wb.info.version.releaseNumber,
                    ModuleInfo.version)))
    txt.write(info_format('Author', grt.root.wb.doc.info.author))
    txt.write(info_format('Caption', grt.root.wb.doc.info.caption))
    txt.write(info_format('Project', grt.root.wb.doc.info.project))
    txt.write(info_format('Changed', grt.root.wb.doc.info.dateChanged))
    txt.write(info_format('Created', grt.root.wb.doc.info.dateCreated))
    txt.write(info_format('Description', grt.root.wb.doc.info.description))

    txt.write('\nPRAGMA foreign_keys = OFF;\n')
    
    lstViwIns = composeSenten(txt,cat)
    addViewInst(lstViwIns,txt)

    sql_text = txt.getvalue()
    txt.close()

    wizard = ExportSQLiteWizard(sql_text)
    wizard.run()

    return 0

class ExportSQLiteWizard_PreviewPage(WizardPage):
    def __init__(self, owner, sql_text):
        WizardPage.__init__(self, owner, 'Review Generated Script')

        self.save_button = mforms.newButton()
        self.save_button.enable_internal_padding(True)
        self.save_button.set_text('Save to File...')
        self.save_button.set_tooltip('Save the text to a new file.')
        self.save_button.add_clicked_callback(self.save_clicked)

        self.copy_button = mforms.newButton()
        self.copy_button.enable_internal_padding(True)
        self.copy_button.set_text('Copy to Clipboard')
        self.copy_button.set_tooltip('Copy the text to the clipboard.')
        self.copy_button.add_clicked_callback(self.copy_clicked)

        self.sql_text = mforms.newCodeEditor()
        self.sql_text.set_language(mforms.LanguageMySQL)
        self.sql_text.set_text(sql_text)

    def go_cancel(self):
        self.main.finish()

    def create_ui(self):
        # buttons for copy to clipboard and save to file are located into button_box
        button_box = mforms.newBox(True)
        button_box.set_padding(8)
        button_box.set_spacing(8)

        button_box.add(self.save_button, False, True)
        button_box.add(self.copy_button, False, True)

        self.content.add_end(button_box, False, True)
        self.content.add_end(self.sql_text, True, True)

    def save_clicked(self):
        file_chooser = mforms.newFileChooser(self.main, mforms.SaveFile)
        file_chooser.set_extensions('SQL Files (*.sql)|*.sql', 'sql')
        if file_chooser.run_modal() == mforms.ResultOk:
            path = file_chooser.get_path()
            text = self.sql_text.get_text(False)
            try:
                with open(path, 'w+') as f:
                    f.write(text)
            except IOError as e:
                mforms.Utilities.show_error(
                    'Save to File',
                    'Could not save to file "%s": %s' % (path, str(e)),
                    'OK')

    def copy_clicked(self):
        mforms.Utilities.set_clipboard_text(self.sql_text.get_text(False))

class ExportSQLiteWizard(WizardForm):
    def __init__(self, sql_text):
        WizardForm.__init__(self, None)

        self.set_name('sqlite_export_wizard')
        self.set_title('SQLite Export Wizard')

        self.preview_page = ExportSQLiteWizard_PreviewPage(self, sql_text)
        self.add_page(self.preview_page)
