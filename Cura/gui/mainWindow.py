#!/usr/bin/env python
# -*- coding: utf-8 -*-

__copyright__ = "Copyright (C) 2013 David Braam - Released under terms of the AGPLv3 License"

import platform
import wx
import os
import webbrowser
import sys
import wx.lib.hyperlink as hl
from wx.lib import scrolledpanel

from Cura.gui import configBase
from Cura.gui import pausePluginPanel
from Cura.gui import configWizard
from Cura.gui import sceneView
from Cura.gui import aboutWindow
from Cura.gui import printerWindow
from Cura.gui.util import dropTarget
from Cura.gui.tools import pidDebugger
from Cura.util import profile
from Cura.util import version
from Cura.util import meshLoader
from Cura.util import resources
from xml.dom import minidom

class mainWindow(wx.Frame):
	def __init__(self):
		super(mainWindow, self).__init__(None, title='Cura by Dagoma 1.0.7', pos=(0, 0), size=wx.DisplaySize())

		wx.EVT_CLOSE(self, self.OnClose)

		# allow dropping any file, restrict later
		self.SetDropTarget(dropTarget.FileDropTarget(self.OnDropFiles))

		frameicon = wx.Icon(resources.getPathForImage('cura.ico'), wx.BITMAP_TYPE_ICO)
		self.SetIcon(frameicon)

		# TODO: wxWidgets 2.9.4 has a bug when NSView does not register for dragged types when wx drop target is set. It was fixed in 2.9.5
		if sys.platform.startswith('darwin'):
			try:
				import objc
				nswindow = objc.objc_object(c_void_p=self.MacGetTopLevelWindowRef())
				view = nswindow.contentView()
				view.registerForDraggedTypes_([u'NSFilenamesPboardType'])
			except:
				pass

		mruFile = os.path.join(profile.getBasePath(), 'mru_filelist.ini')
		self.config = wx.FileConfig(localFilename=mruFile, style=wx.CONFIG_USE_LOCAL_FILE)

		self.ID_MRU_MODEL1, self.ID_MRU_MODEL2, self.ID_MRU_MODEL3, self.ID_MRU_MODEL4, self.ID_MRU_MODEL5, self.ID_MRU_MODEL6, self.ID_MRU_MODEL7, self.ID_MRU_MODEL8, self.ID_MRU_MODEL9, self.ID_MRU_MODEL10 = [wx.NewId() for line in xrange(10)]
		self.modelFileHistory = wx.FileHistory(10, self.ID_MRU_MODEL1)
		self.config.SetPath("/ModelMRU")
		self.modelFileHistory.Load(self.config)

		self.ID_MRU_PROFILE1, self.ID_MRU_PROFILE2, self.ID_MRU_PROFILE3, self.ID_MRU_PROFILE4, self.ID_MRU_PROFILE5, self.ID_MRU_PROFILE6, self.ID_MRU_PROFILE7, self.ID_MRU_PROFILE8, self.ID_MRU_PROFILE9, self.ID_MRU_PROFILE10 = [wx.NewId() for line in xrange(10)]
		self.profileFileHistory = wx.FileHistory(10, self.ID_MRU_PROFILE1)
		self.config.SetPath("/ProfileMRU")
		self.profileFileHistory.Load(self.config)

		self.menubar = wx.MenuBar()
		self.fileMenu = wx.Menu()
		i = self.fileMenu.Append(-1, _("Open an Object") + "\tCTRL+O")
		self.Bind(wx.EVT_MENU, lambda e: self.scene.showLoadModel(), i)
		i = self.fileMenu.Append(-1, _("Save the build plate") + "\tCTRL+S")
		self.Bind(wx.EVT_MENU, lambda e: self.scene.showSaveModel(), i)
		i = self.fileMenu.Append(1, _("Prepare the Print") + "\tCTRL+P")
		self.Bind(wx.EVT_MENU, self.OnPreparePrint, i)

		# Model MRU list
		modelHistoryMenu = wx.Menu()
		self.fileMenu.AppendMenu(wx.NewId(), '&' + _("Recently Opened Objects"), modelHistoryMenu)
		self.modelFileHistory.UseMenu(modelHistoryMenu)
		self.modelFileHistory.AddFilesToMenu()
		self.Bind(wx.EVT_MENU_RANGE, self.OnModelMRU, id=self.ID_MRU_MODEL1, id2=self.ID_MRU_MODEL10)

		self.fileMenu.AppendSeparator()
		i = self.fileMenu.Append(wx.ID_EXIT, _("Quit"))
		self.Bind(wx.EVT_MENU, self.OnQuit, i)
		self.menubar.Append(self.fileMenu, _("File"))

		self.settingsMenu = wx.Menu()
		self.languagesMenu = wx.Menu()
		for language in resources.getLanguageOptions():
			i = self.languagesMenu.Append(-1, _(language[1]), _('You have to reopen the application to load the correct language'), wx.ITEM_RADIO)
			if profile.getPreference('language') == language[1]:
				i.Check(True)
			else:
				i.Check(False)
			def OnLanguageSelect(e, selected_language=language[1]):
				profile.putPreference('language', selected_language)
			self.Bind(wx.EVT_MENU, OnLanguageSelect, i)
		self.settingsMenu.AppendSubMenu(self.languagesMenu, _("Language"))
		i = self.settingsMenu.Append(-1, _("Printers"))
		self.Bind(wx.EVT_MENU, self.OnPrinterWindow, i)
		self.menubar.Append(self.settingsMenu, _("Preferences"))

		contact_url = profile.getPreference('contact_url')
		buy_url = profile.getPreference('buy_url')
		self.helpMenu = wx.Menu()
		i = self.helpMenu.Append(-1, _("Contact us"))
		self.Bind(wx.EVT_MENU, lambda e: webbrowser.open(contact_url), i)
		i = self.helpMenu.Append(-1, _("Buy filament"))
		self.Bind(wx.EVT_MENU, lambda e: webbrowser.open(buy_url), i)
		i = self.helpMenu.Append(-1, _("About"))
		self.Bind(wx.EVT_MENU, self.OnAbout, i)
		self.menubar.Append(self.helpMenu, _("Help"))

		self.SetMenuBar(self.menubar)

		self.statusbar = self.CreateStatusBar(2)
		self.statusbar.SetStatusText('General info')
		self.statusbar.SetStatusText('Slicing info', 1)

		self.splitter = wx.SplitterWindow(self, style = wx.SP_3DSASH | wx.SP_LIVE_UPDATE)
		self.splitter.SetMinimumPaneSize(profile.getPreferenceInt('minimum_pane_size'))
		self.splitter.SetSashGravity(1.0) # Only the SceneView is resized when the windows size is modifed
		self.splitter.Bind(wx.EVT_SPLITTER_DCLICK, lambda evt: evt.Veto())

		self.viewPane = wx.Panel(self.splitter, style=wx.BORDER_NONE)
		#self.optionsPane = wx.Panel(self.splitter, style=wx.BORDER_NONE)
		self.optionsPane = scrolledpanel.ScrolledPanel(self.splitter, style=wx.BORDER_NONE)
		self.optionsPane.SetupScrolling(True, True)

		##Gui components##
		self.normalSettingsPanel = normalSettingsPanel(self.optionsPane, lambda : self.scene.sceneUpdated())

		self.optionsSizer = wx.BoxSizer(wx.VERTICAL)
		self.optionsSizer.Add(self.normalSettingsPanel, 1, wx.EXPAND)
		self.optionsPane.SetSizerAndFit(self.optionsSizer)

		#Preview window
		self.scene = sceneView.SceneView(self.viewPane)

		#Main sizer, to position the preview window, buttons and tab control
		sizer = wx.BoxSizer()
		self.viewPane.SetSizerAndFit(sizer)
		sizer.Add(self.scene, 1, flag=wx.EXPAND)

		self.splitter.SplitVertically(self.viewPane, self.optionsPane, profile.getPreferenceInt('window_normal_sash'))

		# Main window sizer
		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(self.splitter, 1, wx.EXPAND)
		self.SetSizerAndFit(sizer)
		sizer.Layout()

		self.updateProfileToAllControls()

		self.SetBackgroundColour(self.normalSettingsPanel.GetBackgroundColour())

		self.normalSettingsPanel.Show()

		# Set default window size & position
		self.SetSize((wx.Display().GetClientArea().GetWidth()/2, wx.Display().GetClientArea().GetHeight()/2))
		self.SetMinSize((800, 600))
		self.Centre()
		self.Maximize(True)

		if wx.Display.GetFromPoint(self.GetPosition()) < 0:
			self.Centre()
		if wx.Display.GetFromPoint((self.GetPositionTuple()[0] + self.GetSizeTuple()[1], self.GetPositionTuple()[1] + self.GetSizeTuple()[1])) < 0:
			self.Centre()
		if wx.Display.GetFromPoint(self.GetPosition()) < 0:
			self.SetSize((800, 600))
			self.Centre()

		self.scene.updateProfileToControls()
		self.scene._scene.pushFree()
		self.scene.SetFocus()

	def OnPreparePrint(self, e):
		profile.printSlicingInfo()
		self.scene.OnPrintButton(1)
		e.Skip()

	def OnDropFiles(self, files):
		if len(files) > 0:
			self.updateProfileToAllControls()
		self.scene.loadFiles(files)

	def addToProfileMRU(self, file):
		self.profileFileHistory.AddFileToHistory(file)
		self.config.SetPath("/ProfileMRU")
		self.profileFileHistory.Save(self.config)
		self.config.Flush()

	def addToModelMRU(self, file):
		self.modelFileHistory.AddFileToHistory(file)
		self.config.SetPath("/ModelMRU")
		self.modelFileHistory.Save(self.config)
		self.config.Flush()

	def OnProfileMRU(self, e):
		fileNum = e.GetId() - self.ID_MRU_PROFILE1
		path = self.profileFileHistory.GetHistoryFile(fileNum)
		# Update Profile MRU
		self.profileFileHistory.AddFileToHistory(path)  # move up the list
		self.config.SetPath("/ProfileMRU")
		self.profileFileHistory.Save(self.config)
		self.config.Flush()
		# Load Profile
		profile.loadProfile(path)
		self.updateProfileToAllControls()

	def OnModelMRU(self, e):
		fileNum = e.GetId() - self.ID_MRU_MODEL1
		path = self.modelFileHistory.GetHistoryFile(fileNum)
		# Update Model MRU
		self.modelFileHistory.AddFileToHistory(path)  # move up the list
		self.config.SetPath("/ModelMRU")
		self.modelFileHistory.Save(self.config)
		self.config.Flush()
		# Load Model
		profile.putPreference('lastFile', path)
		filelist = [ path ]
		self.scene.loadFiles(filelist)

	def updateProfileToAllControls(self):
		self.scene.OnViewChange()
		self.scene.sceneUpdated()
		if len(self.scene._scene.objects()) > 0:
			self.normalSettingsPanel.pausePluginButton.Enable()
		self.scene.updateProfileToControls()
		self.normalSettingsPanel.updateProfileToControls()

	def reloadSettingPanels(self):
		self.optionsSizer.Detach(self.normalSettingsPanel)
		self.normalSettingsPanel.Destroy()
		self.normalSettingsPanel = normalSettingsPanel(self.optionsPane, lambda : self.scene.sceneUpdated())
		self.optionsSizer.Add(self.normalSettingsPanel, 1, wx.EXPAND)
		self.optionsPane.SetSizerAndFit(self.optionsSizer)
		self.updateProfileToAllControls()

	def OnPrinterWindow(self, e):
		printerBox = printerWindow.printerWindow(self)
		printerBox.Centre()
		printerBox.Show()

	def OnAbout(self, e):
		aboutBox = aboutWindow.aboutWindow(self)
		aboutBox.Centre()
		aboutBox.Show()

	def OnClose(self, e):
		profile.saveProfile(profile.getDefaultProfilePath(), True)
		profile.putPreference('window_normal_sash', int('-' + str(self.optionsPane.GetSize()[0])))

		#HACK: Set the paint function of the glCanvas to nothing so it won't keep refreshing. Which can keep wxWidgets from quiting.
		print "Closing down"
		self.scene.OnPaint = lambda e : e
		self.scene._engine.cleanup()
		self.Destroy()

	def OnQuit(self, e):
		self.Close()

class normalSettingsPanel(configBase.configPanelBase):

	"Main user interface window"
	class Filament:
		def __init__(self):
			self.type = ''
			self.grip_temperature = '185'
			self.print_temperature = '185'
			self.filament_diameter = '1.74'
			self.filament_flow = '80'
			self.retraction_speed = '50'
			self.retraction_amount = '3.5'
			self.filament_physical_density = '1270'
			self.filament_cost_kg = '46'

	class Remplissage:
		def __init__(self):
			self.type = ''
			self.fill_density = ''

	class Precision:
		def __init__(self):
			self.type = ''
			self.layer_height = ''
			self.solid_layer_thickness = ''
			self.wall_thickness = ''
			self.print_speed = ''
			self.temp_preci = ''
			self.travel_speed = ''
			self.bottom_layer_speed = ''
			self.infill_speed = ''
			self.inset0_speed = ''
			self.insetx_speed = ''

	class Tete:
		def __init__(self):
			self.type = ''
			self.fan_speed = ''
			self.cool_min_layer_time = ''

	class Support:
		def __init__(self):
			self.support = None

	class Brim:
		def __init__(self):
			self.platform_adhesion = None

	class PrintingSurface:
		def __init__(self):
			self.name = ''
			self.height = ''

	class Offset:
		def __init__(self):
			self.value = ''
			self.input = ''

	class Palpeur:
		def __init__(self):
			self.palpeur = None

	def __init__(self, parent, callback = None):
		super(normalSettingsPanel, self).__init__(parent, callback)
		self.already_loaded = False
		self.parent = parent
		self.loadxml()
		self.warning_text = wx.StaticText(self, wx.ID_ANY)
		warning_text_font = self.warning_text.GetFont()
		warning_text_font.SetPointSize(10)
		warning_text_font.SetWeight(wx.FONTWEIGHT_BOLD)
		self.warning_text.SetFont(warning_text_font)
		if sys.platform == 'darwin': #Change Combobox to an Choice cause in MAC OS X Combobox have some bug
			self.color_box = wx.Choice(self, wx.ID_ANY, choices = [])
		else:
			self.color_box = wx.ComboBox(self, wx.ID_ANY, choices = [] , style=wx.CB_DROPDOWN | wx.CB_READONLY)

		self.label_4 = wx.StaticText(self, wx.ID_ANY, _(("Temperature (°C) :").decode('utf-8')))
		self.spin_ctrl_1 = wx.SpinCtrl(self, wx.ID_ANY, profile.getProfileSetting('print_temperature'), min=175, max=255, style=wx.SP_ARROW_KEYS | wx.TE_AUTO_URL)
		self.button_1 = wx.Button(self, wx.ID_ANY, _("Prepare the Print"))

		self.offset_label = wx.StaticText(self, wx.ID_ANY, _("Offset (mm) :"))
		self.offset_ctrl = wx.TextCtrl(self, -1, profile.getProfileSetting('offset_input'))

		# Pause plugin
		self.pausePluginButton = wx.Button(self, wx.ID_ANY, _(("Color change(s)")))
		self.pausePluginPanel = pausePluginPanel.pausePluginPanel(self, callback)
		self.__set_properties()
		self.__do_layout()


		self.Init_Palpeur_chbx()
		self.Init_Printing_surface()

		#Refresh ALL Value
		self.Refresh_Supp()
		self.Refresh_Preci()
		self.Refresh_Tet()
		self.Refresh_Fila()
		self.Refresh_Color()
		self.Refresh_SpinCtrl()
		self.Refresh_Rempli()
		self.Refresh_Palpeur_chbx()
		self.Refresh_Printing_surface()
		self.Refresh_Offset()
		self.Refresh_Checkboxbrim()

		profile.saveProfile(profile.getDefaultProfilePath(), True)

		#Evt Select Filament
		if sys.platform == 'darwin':
			self.Bind(wx.EVT_CHOICE, self.EVT_Fila, self.combo_box_1)
			self.Bind(wx.EVT_CHOICE, self.EVT_Color, self.color_box)
		else:
			self.Bind(wx.EVT_COMBOBOX, self.EVT_Fila, self.combo_box_1)
			self.Bind(wx.EVT_COMBOBOX, self.EVT_Color, self.color_box)

		self.Bind(wx.EVT_TEXT, self.EVT_SpinCtrl, self.spin_ctrl_1)
		self.Bind(wx.EVT_TEXT_ENTER, self.EVT_SpinCtrl, self.spin_ctrl_1)
		self.Bind(wx.EVT_SPINCTRL, self.EVT_SpinCtrl, self.spin_ctrl_1)
		self.Bind(wx.EVT_RADIOBOX, self.EVT_Preci, self.radio_box_1)
		self.Bind(wx.EVT_RADIOBOX, self.EVT_Tet, self.tetes_box)
		self.Bind(wx.EVT_RADIOBOX, self.EVT_Supp, self.printsupp)
		self.Bind(wx.EVT_RADIOBOX, self.EVT_Rempl, self.radio_box_2)
		self.Bind(wx.EVT_CHECKBOX, self.EVT_Checkboxpalpeur,self.palpeur_chbx)
		self.Bind(wx.EVT_RADIOBOX, self.EVT_PrtSurf, self.radio_box_3)
		self.Bind(wx.EVT_TEXT, self.EVT_Offset, self.offset_ctrl)
		self.Bind(wx.EVT_CHECKBOX, self.EVT_Checkboxbrim, self.printbrim)
		self.Bind(wx.EVT_BUTTON, self.ClickPreparePrintButton, self.button_1)
		self.Bind(wx.EVT_BUTTON, self.ClickPauseButton, self.pausePluginButton)
 		#self.Bind(wx.EVT_SIZE, self.OnSize)


	def __set_properties(self):
		self.spin_ctrl_1.Enable(False)
		self.printsupp.SetSelection(0)


	def __do_layout(self):
		printername = profile.getMachineSetting('machine_name')
		self.pausePluginButton.Disable()
		self.button_1.Disable()

		language = profile.getPreference("language")
		if language == "French":
			url = "https://dagoma.fr/boutique/filaments.html"
		else:
			url = "https://dagoma3d.com/collections/shop"

		filament_sizer = wx.BoxSizer(wx.HORIZONTAL)
		filament_sizer.Add(wx.StaticText(self, wx.ID_ANY, _("Filament")))
		filament_sizer.Add(wx.StaticText(self, wx.ID_ANY, " ("))
		filament_sizer.Add(hl.HyperLinkCtrl(self, wx.ID_ANY, _("Buy filament"), URL=url))
		filament_sizer.Add(wx.StaticText(self, wx.ID_ANY, "):"))

		main_sizer = wx.BoxSizer(wx.VERTICAL)

		main_sizer.Add(filament_sizer)
		main_sizer.Add(self.combo_box_1, flag=wx.EXPAND|wx.BOTTOM, border=2)
		main_sizer.Add(self.color_box, flag=wx.EXPAND)
		main_sizer.Add(self.warning_text)
		main_sizer.Add(self.label_4)
		main_sizer.Add(self.spin_ctrl_1, flag=wx.EXPAND|wx.BOTTOM, border=5)
		main_sizer.Add(self.radio_box_2, flag=wx.EXPAND|wx.BOTTOM, border=5)
		main_sizer.Add(self.radio_box_1, flag=wx.EXPAND|wx.BOTTOM, border=5)
		if printername == "DiscoEasy200":
			main_sizer.Add(self.tetes_box, flag=wx.EXPAND|wx.BOTTOM, border=5)
		else:
			self.tetes_box.Hide()
		main_sizer.Add(self.printsupp, flag=wx.EXPAND|wx.BOTTOM, border=5)
		if printername == "DiscoVery200":
			main_sizer.Add(self.radio_box_3, flag=wx.EXPAND|wx.BOTTOM, border=5)
			main_sizer.Add(self.offset_label, flag=wx.EXPAND)
			main_sizer.Add(self.offset_ctrl, flag=wx.EXPAND|wx.BOTTOM, border=5)
		else:
			self.radio_box_3.Hide()
			self.offset_label.Hide()
			self.offset_ctrl.Hide()
		if printername != "Neva":
			main_sizer.Add(self.palpeur_chbx)
		else:
			self.palpeur_chbx.Hide()
		main_sizer.Add(self.printbrim, flag=wx.BOTTOM, border=5)
		main_sizer.Add(self.pausePluginButton, flag=wx.EXPAND)
		main_sizer.Add(self.pausePluginPanel, flag=wx.EXPAND)
		main_sizer.Add(self.button_1, flag=wx.EXPAND|wx.TOP, border=5)


		self.SetSizerAndFit(main_sizer)
		self.Layout()

	def loadxml(self):
		xml_file = profile.getPreference('xml_file')
		self.configuration = minidom.parse(resources.getPathForXML(xml_file))
		self.init_Printer()
		self.init_Configuration()
		self.init_GCode()
		self.get_filaments()
		self.get_remplissage()
		self.get_Precision()
		self.get_Tete()
		self.get_support()
		self.get_brim()
		self.get_printing_surface()
		self.get_palpeur()

	def setProfileSetting(self, sub, var):
		value = sub.getElementsByTagName(var)[0].childNodes[0].data
		if value is not None:
			profile.putProfileSetting(var, value)

	def setPreferenceSetting(self, sub, var):
		value = sub.getElementsByTagName(var)[0].childNodes[0].data
		if value is not None:
			profile.putPreference(var, value)

	def setMachineSetting(self, sub, var):
		value = sub.getElementsByTagName(var)[0].childNodes[0].data
		if value is not None:
			profile.putMachineSetting(var, value)

	def init_Printer(self):
		printer = self.configuration.getElementsByTagName('Printer')[0]
		self.setMachineSetting(printer, 'machine_name')
		self.setMachineSetting(printer, 'machine_type')
		self.setMachineSetting(printer, 'machine_width')
		self.setMachineSetting(printer, 'machine_depth')
		self.setMachineSetting(printer, 'machine_height')
		self.setMachineSetting(printer, 'extruder_amount')
		self.setMachineSetting(printer, 'has_heated_bed')
		self.setMachineSetting(printer, 'machine_center_is_zero')
		self.setMachineSetting(printer, 'machine_shape')
		self.setMachineSetting(printer, 'machine_speed_factor')
		self.setMachineSetting(printer, 'extruder_head_size_min_x')
		self.setMachineSetting(printer, 'extruder_head_size_min_y')
		self.setMachineSetting(printer, 'extruder_head_size_max_x')
		self.setMachineSetting(printer, 'extruder_head_size_max_y')
		self.setMachineSetting(printer, 'extruder_head_size_height')
		self.setProfileSetting(printer, 'nozzle_size')
		self.setProfileSetting(printer, 'retraction_enable')

	def init_Configuration(self):
		global_config = self.configuration.getElementsByTagName('Configuration')[0]
		if global_config is not None:
			config = global_config
		else:
			config = self.configuration.getElementsByTagName('Config_Adv')[0]

		self.setProfileSetting(config, 'bottom_thickness')
		self.setProfileSetting(config, 'layer0_width_factor')
		self.setProfileSetting(config, 'object_sink')
		self.setProfileSetting(config, 'fan_enabled')

		if global_config is not None:
			config = global_config
		else:
			config = self.configuration.getElementsByTagName('Config_Expert')[0]
		# Retraction
		self.setProfileSetting(config, 'retraction_min_travel')
		self.setProfileSetting(config, 'retraction_combing')
		self.setProfileSetting(config, 'retraction_minimal_extrusion')
		self.setProfileSetting(config, 'retraction_hop')
		# Skirt
		self.setProfileSetting(config, 'skirt_line_count')
		self.setProfileSetting(config, 'skirt_gap')
		self.setProfileSetting(config, 'skirt_minimal_length')
		# Cool
		self.setProfileSetting(config, 'fan_full_height')
		#self.setProfileSetting(config, 'fan_speed')
		self.setProfileSetting(config, 'fan_speed_max')
		self.setProfileSetting(config, 'cool_min_feedrate')
		self.setProfileSetting(config, 'cool_head_lift')
		# Infill
		self.setProfileSetting(config, 'solid_top')
		self.setProfileSetting(config, 'solid_bottom')
		self.setProfileSetting(config, 'fill_overlap')
		# Support
		self.setProfileSetting(config, 'support_type')
		self.setProfileSetting(config, 'support_angle')
		self.setProfileSetting(config, 'support_fill_rate')
		self.setProfileSetting(config, 'support_xy_distance')
		self.setProfileSetting(config, 'support_z_distance')
		# Block Magic
		self.setProfileSetting(config, 'spiralize')
		self.setProfileSetting(config, 'simple_mode')
		# Brim
		self.setProfileSetting(config, 'brim_line_count')
		# Raft
		self.setProfileSetting(config, 'raft_margin')
		self.setProfileSetting(config, 'raft_line_spacing')
		self.setProfileSetting(config, 'raft_base_thickness')
		self.setProfileSetting(config, 'raft_base_linewidth')
		self.setProfileSetting(config, 'raft_interface_thickness')
		self.setProfileSetting(config, 'raft_interface_linewidth')
		self.setProfileSetting(config, 'raft_airgap')
		self.setProfileSetting(config, 'raft_surface_layers')
		# Fix Horrible
		self.setProfileSetting(config, 'fix_horrible_union_all_type_a')
		self.setProfileSetting(config, 'fix_horrible_union_all_type_b')
		self.setProfileSetting(config, 'fix_horrible_use_open_bits')
		self.setProfileSetting(config, 'fix_horrible_extensive_stitching')

		if global_config is not None:
			config = global_config
		else:
			config = self.configuration.getElementsByTagName('Config_Preferences')[0]
		#Cura Settings
		self.setPreferenceSetting(config, 'auto_detect_sd')

	def init_GCode(self):
		gcode = self.configuration.getElementsByTagName("GCODE")[0]
		gcode_start = gcode.getElementsByTagName("Gstart")[0].childNodes[0].data
		profile.putAlterationSetting('start.gcode', gcode_start)

		gcode_end = gcode.getElementsByTagName("Gend")[0].childNodes[0].data
		profile.putAlterationSetting('end.gcode', gcode_end)

	def get_filaments(self):
		filaments = self.configuration.getElementsByTagName('Filament')
		self.filaments = []
		choices = []
		for filament in filaments:
			if filament.hasAttributes():
				fila = self.Filament()
				name = filament.getAttribute("name")
				choices.append(_(name))
				fila.type = name
			try :
				if len(filament.getElementsByTagName("grip_temperature")) > 0 is not None:
					fila.grip_temperature = filament.getElementsByTagName("grip_temperature")[0].childNodes[0].data
				else:
					fila.grip_temperature = filament.getElementsByTagName("print_temperature")[0].childNodes[0].data
				fila.print_temperature = filament.getElementsByTagName("print_temperature")[0].childNodes[0].data
				fila.filament_diameter = filament.getElementsByTagName("filament_diameter")[0].childNodes[0].data
				fila.filament_flow = filament.getElementsByTagName("filament_flow")[0].childNodes[0].data
				fila.retraction_speed = filament.getElementsByTagName("retraction_speed")[0].childNodes[0].data
				fila.retraction_amount = filament.getElementsByTagName("retraction_amount")[0].childNodes[0].data
				fila.filament_physical_density = filament.getElementsByTagName("filament_physical_density")[0].childNodes[0].data
				fila.filament_cost_kg = filament.getElementsByTagName("filament_cost_kg")[0].childNodes[0].data
				self.filaments.append(fila)
			except:
				print 'Some Error in Filament Bloc'
				pass

		if sys.platform == 'darwin': #Change Combobox to an Choice cause in MAC OS X Combobox have some bug
			self.combo_box_1 = wx.Choice(self, wx.ID_ANY, choices = choices)
		else:
			self.combo_box_1 = wx.ComboBox(self, wx.ID_ANY, choices = choices , style=wx.CB_DROPDOWN | wx.CB_READONLY)
		self.combo_box_1.SetSelection(int(profile.getPreference('filament_index')))

	def get_remplissage(self):
		bloc_name = _("Filling density :")
		remplissages = self.configuration.getElementsByTagName("Filling")
		if len(remplissages) == 0:
			remplissages = self.configuration.getElementsByTagName("Remplissage")
		choices = []
		self.remplissages = []
		for remplissage in remplissages:
			if remplissage.hasAttributes():
				rempli = self.Remplissage()
				name = _(remplissage.getAttribute("name"))
				choices.append(name)
				rempli.type = name
				try :
					rempli.fill_density = remplissage.getElementsByTagName("fill_density")[0].childNodes[0].data
					self.remplissages.append(rempli)
				except:
					print 'Some Errors in Remplissage Bloc'
					pass
		self.radio_box_2 = wx.RadioBox(self, wx.ID_ANY, bloc_name, choices = choices, majorDimension=0, style=wx.RA_SPECIFY_ROWS)
		self.radio_box_2.SetSelection(int(profile.getPreference('fill_index')))

	def get_Precision(self):
		bloc_name = _("Quality (layer thickness) :")
		precisions = self.configuration.getElementsByTagName("Precision")
		choices = []
		self.precisions = []
		for precision in precisions:
			if precision.hasAttributes():
				preci = self.Precision()
				name = precision.getAttribute("name")
				choices.append(_(name))
				preci.type = name
				try :
					preci.layer_height = precision.getElementsByTagName("layer_height")[0].childNodes[0].data
					preci.solid_layer_thickness = precision.getElementsByTagName("solid_layer_thickness")[0].childNodes[0].data
					preci.wall_thickness = precision.getElementsByTagName("wall_thickness")[0].childNodes[0].data
					preci.print_speed = precision.getElementsByTagName("print_speed")[0].childNodes[0].data
					preci.temp_preci = precision.getElementsByTagName("temp_preci")[0].childNodes[0].data
					preci.travel_speed = precision.getElementsByTagName("travel_speed")[0].childNodes[0].data
					preci.bottom_layer_speed = precision.getElementsByTagName("bottom_layer_speed")[0].childNodes[0].data
					preci.infill_speed = precision.getElementsByTagName("infill_speed")[0].childNodes[0].data
					preci.inset0_speed = precision.getElementsByTagName("inset0_speed")[0].childNodes[0].data
					preci.insetx_speed = precision.getElementsByTagName("insetx_speed")[0].childNodes[0].data
					self.precisions.append(preci)
				except :
					print 'Some Error in Precision Bloc'
					pass
		self.radio_box_1 = wx.RadioBox(self, wx.ID_ANY, bloc_name, choices=choices, majorDimension=0, style=wx.RA_SPECIFY_ROWS)
		self.radio_box_1.SetSelection(int(profile.getPreference('precision_index')))

	def get_Tete(self):
		bloc_name = _("Printhead version :")
		tetes = self.configuration.getElementsByTagName("PrinterHead")
		if len(tetes) == 0:
			tetes = self.configuration.getElementsByTagName("Tete")
		choices = []
		self.tetes = []
		for tete in tetes:
			if tete.hasAttributes():
				tet = self.Tete()
				name = tete.getAttribute("name")
				choices.append(_(name))
				tet.type = name
				try :
					tet.fan_speed = tete.getElementsByTagName("fan_speed")[0].childNodes[0].data
					tet.cool_min_layer_time = tete.getElementsByTagName("cool_min_layer_time")[0].childNodes[0].data
					self.tetes.append(tet)
				except :
					print 'Some Error in Tete Bloc'
					pass
		self.tetes_box = wx.RadioBox(self, wx.ID_ANY, bloc_name, choices=choices, majorDimension=0, style=wx.RA_SPECIFY_ROWS)
		self.tetes_box.SetSelection(int(profile.getPreference('printhead_index')))

	def get_support(self):
		bloc_name = _("Printing supports :")
		supports = self.configuration.getElementsByTagName("Support")
		choices = []
		self.supports = []
		for support in supports:
			if support.hasAttributes():
				supp = self.Support()
				name = _(support.getAttribute("name"))
				choices.append(name)
				supp.type = name
				try :
					supp.support = support.getElementsByTagName("support")[0].childNodes[0].data
					self.supports.append(supp)
				except :
					print 'Some Error in Supports Bloc'
					pass
		self.printsupp = wx.RadioBox(self, wx.ID_ANY, bloc_name, choices=choices, majorDimension=0, style=wx.RA_SPECIFY_ROWS)

	def get_brim(self):
		bloc_name = _("Improve the adhesion surface")
		self.printbrim = wx.CheckBox(self, wx.ID_ANY, bloc_name)
		brim_enable = self.configuration.getElementsByTagName("Brim_Enable")[0]
		brim_disable = self.configuration.getElementsByTagName("Brim_Disable")[0]
		self.brims = []
		self.brims.append(self.Brim())
		self.brims[0].platform_adhesion = brim_enable.getElementsByTagName("platform_adhesion")[0].childNodes[0].data
		self.brims.append(self.Brim())
		self.brims[1].platform_adhesion = brim_disable.getElementsByTagName("platform_adhesion")[0].childNodes[0].data

	# Fonction qui recupere dans le xml les differentes lignes pour le bloc Palpeur
	def get_palpeur(self):
		bloc_name = _("Use the sensor")
		self.palpeur_chbx = wx.CheckBox(self, wx.ID_ANY, bloc_name)
		palpeur_enable = self.configuration.getElementsByTagName("Sensor_Enable")
		if len(palpeur_enable) == 0:
			palpeur_enable = self.configuration.getElementsByTagName("Palpeur_Enable")
			sensor_enabled = palpeur_enable[0].getElementsByTagName("palpeur")[0].childNodes[0].data
		else:
			sensor_enabled = palpeur_enable[0].getElementsByTagName("value")[0].childNodes[0].data
		palpeur_disable = self.configuration.getElementsByTagName("Sensor_Disable")
		if len(palpeur_disable) == 0:
			palpeur_disable = self.configuration.getElementsByTagName("Palpeur_Disable")
			sensor_disabled = palpeur_disable[0].getElementsByTagName("palpeur")[0].childNodes[0].data
		else:
			sensor_disabled = palpeur_disable[0].getElementsByTagName("value")[0].childNodes[0].data
		self.palpeurs = []
		self.palpeurs.append(self.Palpeur())
		self.palpeurs[0].palpeur = sensor_enabled
		self.palpeurs.append(self.Palpeur())
		self.palpeurs[1].palpeur = sensor_disabled

	def get_printing_surface(self):
		bloc_name = _("Printing surface :")

		printing_surfaces = self.configuration.getElementsByTagName("Printing_surface")
		if len(printing_surfaces) == 0:
			printing_surfaces = self.configuration.getElementsByTagName("PrintingSurface")
		choices = []
		self.printing_surfaces = []

		for printing_surface in printing_surfaces:
			if printing_surface.hasAttributes():
				prtsurf = self.PrintingSurface()
				name = printing_surface.getAttribute("name")
				choices.append(_(name))
				prtsurf.name = name
				try :
					prtsurf.height = printing_surface.getElementsByTagName("printing_surface_height")[0].childNodes[0].data
					self.printing_surfaces.append(prtsurf)
				except :
					print 'Some Error in Printing Surface Bloc'
					pass

		if len(choices) == 0:
			name = "Generic"
			choices.append(name)
			prtsurf = self.PrintingSurface()
			prtsurf.name = name
			prtsurf.height = 0.0
			self.printing_surfaces.append(prtsurf)
		self.radio_box_3 = wx.RadioBox(self, wx.ID_ANY, bloc_name, choices=choices, majorDimension=0, style=wx.RA_SPECIFY_ROWS)

	def Refresh_Fila(self):
		#print "Refresh fila"
		filament_index = self.combo_box_1.GetSelection()
		fila = self.filaments[filament_index]
		profile.putPreference('filament_index', filament_index)
		profile.putPreference('filament_name', fila.type)
		profile.putProfileSetting('grip_temperature', fila.grip_temperature)
		calculated_print_temperature = float(fila.print_temperature)
		if fila.type == 'Other PLA type' or fila.type == 'Autre PLA':
			self.warning_text.SetLabel(_("This setting must be used with caution!"))
			self.warning_text.SetForegroundColour((169, 68, 66))
			self.spin_ctrl_1.Enable(True)
		else:
			calculated_print_temperature += self.temp_preci
			self.warning_text.SetLabel(_("Filament approved by Dagoma."))
			self.warning_text.SetForegroundColour((60, 118, 61))
			self.spin_ctrl_1.Enable(False)
		profile.putProfileSetting('print_temperature', str(calculated_print_temperature))
		self.spin_ctrl_1.SetValue(calculated_print_temperature)
		profile.putProfileSetting('filament_diameter', fila.filament_diameter)
		profile.putProfileSetting('filament_flow', fila.filament_flow)
		profile.putProfileSetting('retraction_speed', fila.retraction_speed)
		profile.putProfileSetting('retraction_amount', fila.retraction_amount)
		profile.putProfileSetting('filament_physical_density', fila.filament_physical_density)
		profile.putProfileSetting('filament_cost_kg', fila.filament_cost_kg)

		self.color_box.Clear()
		self.color_box.Append(_("Generic"))
		filaments = self.configuration.getElementsByTagName("Filament")
		colors = filaments[filament_index].getElementsByTagName("Color")
		if len(colors) > 0:
			self.color_box.Enable(True)
			for color in colors:
				if color.hasAttributes():
					name = _(color.getAttribute("name"))
					self.color_box.Append(name)
		else:
			self.color_box.Enable(False)

		if not self.already_loaded:
			color_index = int(profile.getPreference('color_index')) + 1
			self.color_box.SetSelection(color_index)
			self.already_loaded = True
		else:
			self.color_box.SetSelection(0)
			profile.putPreference('color_index', -1)

	def Refresh_Color(self):
		#print 'Refresh color'
		color_index = self.color_box.GetSelection() - 1
		profile.putPreference('color_index', color_index)
		filament_index = int(profile.getPreference('filament_index'))
		fila = self.filaments[filament_index]
		if color_index > -1:
			filaments = self.configuration.getElementsByTagName("Filament")
			colors = filaments[filament_index].getElementsByTagName("Color")
			color = colors[color_index]

			print_temperature = color.getElementsByTagName("print_temperature")[0].childNodes[0].data
			if print_temperature is None:
				print_temperature = float(fila.print_temperature)
			else:
				print_temperature = float(print_temperature)
			if not self.spin_ctrl_1.IsEnabled():
				print_temperature += self.temp_preci
			self.spin_ctrl_1.SetValue(print_temperature)
			profile.putProfileSetting('print_temperature', str(print_temperature))

			grip_temperature = color.getElementsByTagName("grip_temperature")[0].childNodes[0].data
			if grip_temperature is None:
				grip_temperature = fila.grip_temperature
			profile.putProfileSetting('grip_temperature', str(grip_temperature))

			filament_diameter = color.getElementsByTagName("filament_diameter")[0].childNodes[0].data
			if filament_diameter is None:
				filament_diameter = fila.filament_diameter
			profile.putProfileSetting('filament_diameter', str(filament_diameter))

			filament_flow = color.getElementsByTagName("filament_flow")[0].childNodes[0].data
			if filament_flow is None:
				filament_flow = fila.filament_flow
			profile.putProfileSetting('filament_flow', str(filament_flow))

			retraction_speed = color.getElementsByTagName("retraction_speed")[0].childNodes[0].data
			if retraction_speed is None:
				retraction_speed = fila.retraction_speed
			profile.putProfileSetting('retraction_speed', str(retraction_speed))

			retraction_amount = color.getElementsByTagName("retraction_amount")[0].childNodes[0].data
			if retraction_amount is None:
				retraction_amount = fila.retraction_amount
			profile.putProfileSetting('retraction_amount', str(retraction_amount))

			filament_physical_density = color.getElementsByTagName("filament_physical_density")[0].childNodes[0].data
			if filament_physical_density is None:
				filament_physical_density = fila.filament_physical_density
			profile.putProfileSetting('filament_physical_density', str(filament_physical_density))

			filament_cost_kg = color.getElementsByTagName("filament_cost_kg")[0].childNodes[0].data
			if filament_cost_kg is None:
				filament_cost_kg = fila.filament_cost_kg
			profile.putProfileSetting('filament_cost_kg', str(filament_cost_kg))
		else:
			print_temperature = float(fila.print_temperature)
			if not self.spin_ctrl_1.IsEnabled():
				print_temperature += self.temp_preci
			self.spin_ctrl_1.SetValue(print_temperature)
			profile.putProfileSetting('print_temperature', str(print_temperature))
			profile.putProfileSetting('grip_temperature', fila.grip_temperature)
			profile.putProfileSetting('filament_diameter', fila.filament_diameter)
			profile.putProfileSetting('filament_flow', fila.filament_flow)
			profile.putProfileSetting('retraction_speed', fila.retraction_speed)
			profile.putProfileSetting('retraction_amount', fila.retraction_amount)
			profile.putProfileSetting('filament_physical_density', fila.filament_physical_density)
			profile.putProfileSetting('filament_cost_kg', fila.filament_cost_kg)

	def Refresh_SpinCtrl(self):
		#print 'Refresh Spin'
		profile.putProfileSetting('print_temperature', str(self.spin_ctrl_1.GetValue()))

	def Refresh_Rempli(self):
		fill_index = self.radio_box_2.GetSelection()
		rempli = self.remplissages[fill_index]
		profile.putPreference('fill_index', fill_index)
		profile.putProfileSetting('fill_density', rempli.fill_density)

	def Refresh_Preci(self):
		precision_index = self.radio_box_1.GetSelection()
		preci = self.precisions[precision_index]
		profile.putPreference('precision_index', precision_index)
		profile.putProfileSetting('layer_height', preci.layer_height)
		profile.putProfileSetting('solid_layer_thickness', preci.solid_layer_thickness)
		profile.putProfileSetting('wall_thickness', preci.wall_thickness)
		profile.putProfileSetting('print_speed', preci.print_speed)
		new_temp_preci = float(preci.temp_preci)
		calculated_print_temperature = float(profile.getProfileSetting('print_temperature'))
		if not self.spin_ctrl_1.IsEnabled():
			calculated_print_temperature += new_temp_preci
			try:
				calculated_print_temperature -= self.temp_preci
			except:
				pass
		self.temp_preci = new_temp_preci
		self.spin_ctrl_1.SetValue(calculated_print_temperature)
		profile.putProfileSetting('print_temperature', str(calculated_print_temperature))
		profile.putProfileSetting('travel_speed', preci.travel_speed)
		profile.putProfileSetting('bottom_layer_speed', preci.bottom_layer_speed)
		# Speed
		profile.putProfileSetting('infill_speed', preci.infill_speed)
		profile.putProfileSetting('inset0_speed', preci.inset0_speed)
		profile.putProfileSetting('insetx_speed', preci.insetx_speed)

		# Refresh layer heights according to quality...
		for panel in self.pausePluginPanel.panelList:
			panelChildren = panel.GetSizer().GetChildren()
			height_value = None
			layerWidget = None
			heightWidget = None
			for panelChild in panelChildren:
				panelWidget = panelChild.GetWindow()
				# The only enabled textctrl by line is the one containing the layer info
				if isinstance(panelWidget, wx.TextCtrl) and panelWidget.IsEnabled():
					layerWidget = panelWidget
				# The only disabled textctrl by line is the one containing the height info
				if isinstance(panelWidget, wx.TextCtrl) and not panelWidget.IsEnabled():
					heightWidget = panelWidget
			heightValue = heightWidget.GetValue().split(' mm')[0]
			layerWidget.SetValue(str(int(float(heightValue) / float(preci.layer_height))))

	def Refresh_Tet(self):
		printhead_index = self.tetes_box.GetSelection()
		tet = self.tetes[printhead_index]
		profile.putPreference('printhead_index', printhead_index)
		profile.putProfileSetting('fan_speed', tet.fan_speed)
		profile.putProfileSetting('cool_min_layer_time', tet.cool_min_layer_time)

	def Refresh_Supp(self):
		supp = self.supports[self.printsupp.GetSelection()]
		profile.putProfileSetting('support', supp.support)

	def Refresh_Checkboxbrim(self):
		if self.printbrim.GetValue():
			profile.putProfileSetting('platform_adhesion', self.brims[0].platform_adhesion)
		else:
			profile.putProfileSetting('platform_adhesion', self.brims[1].platform_adhesion)

	# fonction pour initialiser la checkbox palpeur dans le profil
	def Init_Palpeur_chbx(self):
		if profile.getProfileSetting('palpeur_enable') == 'Palpeur' or profile.getProfileSetting('palpeur_enable') == 'Enabled':
			self.palpeur_chbx.SetValue(True)
		else :
			self.palpeur_chbx.SetValue(False)
		self.palpeur_chbx.Refresh()

	#fonction pour initialiser la checkbox palpeur dans le profil
	def Init_Printing_surface(self):
		self.radio_box_3.SetStringSelection(profile.getProfileSetting('printing_surface_name'))
		self.radio_box_3.Refresh()

	#fonction qui verif si un str est un floatant
	#
	#
	def is_number(self, zeString):
		try:
			float(zeString)
			return True
		except ValueError:
			return False


	#fonction pour calcul l'offset en fonction
	#
	#
	def calculateZOffset(self):
		printing_surface_height = float(profile.getProfileSetting('printing_surface_height'))
		offset_input = float(profile.getProfileSetting('offset_input'))
		offset_value = offset_input - printing_surface_height
		profile.putProfileSetting('offset_value', offset_value)


	#fonction pour enregistrer les données relative à la surface d'impresion dans le profil
	#
	#
	def Refresh_Printing_surface(self):
		prtsurf = self.printing_surfaces[self.radio_box_3.GetSelection()]
		profile.putProfileSetting('printing_surface_name', prtsurf.name)
		profile.putProfileSetting('printing_surface_height', prtsurf.height)
		self.calculateZOffset()


	#fonction pour enregistrer les données relative à l'offset dans le profil
	#
	#
	def Refresh_Offset(self):
		valu = self.offset_ctrl.GetValue()
		if self.is_number(valu) :
			profile.putProfileSetting('offset_input', self.offset_ctrl.GetValue())
			self.calculateZOffset()
		else :
			self.offset_ctrl.SetValue(profile.getProfileSetting('offset_input'))
			self.offset_ctrl.Refresh()

	# fonction pour enregistrer les données relative au palpeur dans le profil
	def Refresh_Palpeur_chbx(self):
		if self.palpeur_chbx.GetValue():
			sensor_value = self.palpeurs[0].palpeur
		else:
			sensor_value = self.palpeurs[1].palpeur
		profile.putProfileSetting('palpeur_enable', sensor_value)

	def EVT_Supp(self, event):
		self.Refresh_Supp()
		profile.saveProfile(profile.getDefaultProfilePath(), True)
		self.GetParent().GetParent().GetParent().scene.updateProfileToControls()
		self.GetParent().GetParent().GetParent().scene.sceneUpdated()
		event.Skip()

	def EVT_Checkboxbrim(self, event):
		self.Refresh_Checkboxbrim()
		profile.saveProfile(profile.getDefaultProfilePath(), True)
		self.GetParent().GetParent().GetParent().scene.updateProfileToControls()
		self.GetParent().GetParent().GetParent().scene.sceneUpdated()
		event.Skip()

	def EVT_Preci(self, event):
		self.Refresh_Preci()
		profile.saveProfile(profile.getDefaultProfilePath(), True)
		self.GetParent().GetParent().GetParent().scene.updateProfileToControls()
		self.GetParent().GetParent().GetParent().scene.sceneUpdated()
		event.Skip()

	def EVT_Tet(self, event):
		self.Refresh_Tet()
		profile.saveProfile(profile.getDefaultProfilePath(), True)
		self.GetParent().GetParent().GetParent().scene.updateProfileToControls()
		self.GetParent().GetParent().GetParent().scene.sceneUpdated()
		event.Skip()

	def EVT_Rempl(self, event):
		self.Refresh_Rempli()
		profile.saveProfile(profile.getDefaultProfilePath(), True)
		self.GetParent().GetParent().GetParent().scene.updateProfileToControls()
		self.GetParent().GetParent().GetParent().scene.sceneUpdated()
		event.Skip()

	def EVT_Fila(self, event):
		self.Refresh_Fila()
		profile.saveProfile(profile.getDefaultProfilePath(), True)
		self.GetParent().GetParent().GetParent().scene.updateProfileToControls()
		self.GetParent().GetParent().GetParent().scene.sceneUpdated()
		event.Skip()

	def EVT_Color(self, event):
		self.Refresh_Color()
		profile.saveProfile(profile.getDefaultProfilePath(), True)
		self.GetParent().GetParent().GetParent().scene.updateProfileToControls()
		self.GetParent().GetParent().GetParent().scene.sceneUpdated()
		event.Skip()

	def EVT_SpinCtrl(self, event):
		self.Refresh_SpinCtrl()
		profile.saveProfile(profile.getDefaultProfilePath(), True)
		self.GetParent().GetParent().GetParent().scene.updateProfileToControls()
		self.GetParent().GetParent().GetParent().scene.sceneUpdated()
		event.Skip()

	# evenement sur le bloc Printing Surface
	#
	#
	def EVT_PrtSurf(self, event):
		self.Refresh_Printing_surface()
		profile.saveProfile(profile.getDefaultProfilePath(), True)
		self.GetParent().GetParent().GetParent().scene.updateProfileToControls()
		self.GetParent().GetParent().GetParent().scene.sceneUpdated()
		event.Skip()


	# evenement sur le l'input pour l'Offset
	#
	#
	def EVT_Offset(self, event):
		self.Refresh_Offset()
		profile.saveProfile(profile.getDefaultProfilePath(), True)
		self.GetParent().GetParent().GetParent().scene.updateProfileToControls()
		self.GetParent().GetParent().GetParent().scene.sceneUpdated()
		event.Skip()


	# evenement sur le bloc palpeur
	def EVT_Checkboxpalpeur(self, event):
		self.Refresh_Palpeur_chbx()
		profile.saveProfile(profile.getDefaultProfilePath(), True)
		self.GetParent().GetParent().GetParent().scene.updateProfileToControls()
		self.GetParent().GetParent().GetParent().scene.sceneUpdated()
		event.Skip()


	def ClickPreparePrintButton(self, event):
		profile.printSlicingInfo()
		self.GetParent().GetParent().GetParent().scene.OnPrintButton(1)
		event.Skip()

	def ClickPauseButton(self, event):
		scene_viewSelection = self.GetParent().GetParent().GetParent().scene.viewSelection
		if scene_viewSelection.getValue() == 0:
			scene_viewSelection.setValue(1)
		else:
			scene_viewSelection.setValue(0)
		event.Skip()

	def OnSize(self, e):
		e.Skip()

	def updateProfileToControls(self):
		super(normalSettingsPanel, self).updateProfileToControls()
		self.pausePluginPanel.updateProfileToControls()
