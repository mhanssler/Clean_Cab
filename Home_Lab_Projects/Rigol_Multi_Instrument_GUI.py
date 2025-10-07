#!/usr/bin/env python3
"""
Rigol Multi-Instrument Control System - GUI Version
Advanced graphical interface for controlling Rigol lab equipment
Supports DP832, DL3000, and DS1102E via SSH connection to Raspberry Pi

Features:
- Real-time measurement displays
- Interactive instrument controls
- Live data plotting
- Professional tabbed interface
- Emergency shutdown controls
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.animation import FuncAnimation
import numpy as np
import threading
import queue
import time
import os
from datetime import datetime

# Import the backend controller
from Connect_to_Rigol_Instruments import connect_to_instrument, disconnect_from_instrument, send_command

class RigolGUI:
    """
    Main GUI class for Rigol Multi-Instrument Control System
    """
    
    def __init__(self, root):
        self.root = root
        self.root.title("🔬 Rigol Multi-Instrument Control System")
        self.root.geometry("1400x900")
        self.root.configure(bg='#2b2b2b')
        
        # Scaling and font management
        self.setup_scaling()
        
        # Configure style for dark theme
        self.setup_styles()
        
        # Command verification system
        self.command_timeout = 5.0  # seconds
        self.max_retries = 3
        self.command_history = []
        self.failed_commands = []
        
        # Track initial window size for scaling calculations
        self.initial_width = 1400
        self.initial_height = 900
        
        # Backend controller
        self.ssh_connection = None
        self.connected = False
        self.auto_refresh_enabled = False
        
        # Data queues for real-time updates
        self.measurement_queue = queue.Queue()
        self.log_queue = queue.Queue()
        
        # Measurement history for plotting
        self.measurement_history = {
            'power_supply': {
                'time': [],
                'ch1_voltage': [], 'ch1_current': [], 'ch1_power': [],
                'ch2_voltage': [], 'ch2_current': [], 'ch2_power': [],
                'ch3_voltage': [], 'ch3_current': [], 'ch3_power': []
            },
            'electronic_load': {
                'time': [],
                'voltage': [], 'current': [], 'power': []
            },
            'oscilloscope': {
                'time': [],
                'ch1_data': [], 'ch2_data': []
            }
        }
        
        # Instrument status
        self.instruments = {
            'power_supply': {
                'model': 'DP832',
                'resource': None,
                'status': 'not_connected'
            },
            'electronic_load': {
                'model': 'DL3000',
                'resource': None,
                'status': 'not_connected'
            },
            'oscilloscope': {
                'model': 'DS1102E',
                'resource': None,
                'status': 'not_connected'
            }
        }
        
        # Power Supply Status
        def _make_power_channel(v_limit, i_limit):
            return {
                'set_voltage': 0.0,
                'set_current': 0.0,
                'meas_voltage': 0.0,
                'meas_current': 0.0,
                'power': 0.0,
                'output': False,
                'voltage_limit': v_limit,
                'current_limit': i_limit
            }

        self.power_supply_status = {
            1: _make_power_channel(30.0, 3.0),
            2: _make_power_channel(30.0, 3.0),
            3: _make_power_channel(5.0, 3.0)
        }
        
        # Electronic Load Status
        self.load_status = {
            'mode': 'CC',
            'voltage': 0.0, 'current': 0.0, 'power': 0.0, 'resistance': 0.0,
            'input': False
        }

        # Oscilloscope Status
        self.scope_status = {
            'timebase': 1e-3,
            'trigger_mode': 'AUTO',
            'channel_1': {'enabled': True, 'scale': '1.0', 'offset': 0.0},
            'channel_2': {'enabled': False, 'scale': '1.0', 'offset': 0.0}
        }

        # Layout defaults for consistent spacing
        self.layout = {
            'outer_padx': 24,
            'outer_pady': 20,
            'section_pad': 18,
            'inner_pad': 12
        }
        
        # Create GUI components
        self.create_gui()
        
        # Start background threads
        self.start_background_threads()
        
        # Setup window close handler
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Bind window resize events for scaling
        self.root.bind("<Configure>", self.on_window_resize)
    
    def setup_scaling(self):
        """Setup dynamic text and UI scaling"""
        # Initialize scale factor first
        self.scale_factor = 1.0
        
        # Base font sizes (will be scaled)
        self.base_fonts = {
            'title': 14,
            'heading': 12,
            'normal': 10,
            'small': 8,
            'button': 9,
            'status': 10
        }
        
        # Current scaled fonts
        self.fonts = self.base_fonts.copy()

        # Base dimensions for widgets (will scale with window)
        self.base_dimensions = {
            'scale_length': 260,
            'entry_width': 10,
            'combo_width': 14,
            'tree_column_width': 110
        }

        self.dimensions = self.base_dimensions.copy()

        # Registry of widgets that need dynamic resizing
        self.widget_registry = {
            'scales': [],
            'entries': [],
            'combos': [],
            'trees': []
        }
        
        # DPI awareness
        try:
            import tkinter.font as tkFont
            self.default_font = tkFont.nametofont("TkDefaultFont")
            self.text_font = tkFont.nametofont("TkTextFont")
            self.fixed_font = tkFont.nametofont("TkFixedFont")
        except:
            pass
    
    def update_scaling(self, scale_factor):
        """Update all fonts and UI elements based on scale factor"""
        self.scale_factor = scale_factor
        
        # Update font sizes
        for font_type, base_size in self.base_fonts.items():
            self.fonts[font_type] = max(8, int(base_size * scale_factor))

        # Update widget dimensions
        self.dimensions['scale_length'] = max(180, int(self.base_dimensions['scale_length'] * scale_factor))
        self.dimensions['entry_width'] = max(8, int(self.base_dimensions['entry_width'] * scale_factor))
        self.dimensions['combo_width'] = max(10, int(self.base_dimensions['combo_width'] * scale_factor))
        self.dimensions['tree_column_width'] = max(90, int(self.base_dimensions['tree_column_width'] * scale_factor))
        
        # Update ttk styles with new font sizes
        self.update_font_styles()
        
        # Update matplotlib figure size if it exists
        if hasattr(self, 'fig'):
            new_figsize = (12 * scale_factor, 6 * scale_factor)
            self.fig.set_size_inches(new_figsize)
            if hasattr(self, 'canvas'):
                self.canvas.draw()
        
        # Update oscilloscope figure size if it exists
        if hasattr(self, 'scope_fig'):
            scope_figsize = (10 * scale_factor, 6 * scale_factor)
            self.scope_fig.set_size_inches(scope_figsize)
            if hasattr(self, 'scope_canvas'):
                self.scope_canvas.draw()
        
        # Update font sizes for direct tkinter widgets (like labels in overview)
        self.update_direct_widget_fonts()

        # Apply dimension changes to registered widgets
        self.update_widget_dimensions()
    
    def update_direct_widget_fonts(self):
        """Update fonts for direct tkinter widgets that don't use ttk styles"""
        try:
            # Update power supply overview labels
            if hasattr(self, 'ps_overview_labels'):
                for ch in self.ps_overview_labels:
                    for widget in self.ps_overview_labels[ch].values():
                        if hasattr(widget, 'configure'):
                            widget.configure(font=('Arial', self.fonts['normal']))
            
            # Update load overview labels
            if hasattr(self, 'load_overview_labels'):
                for widget in self.load_overview_labels.values():
                    if hasattr(widget, 'configure'):
                        widget.configure(font=('Arial', self.fonts['normal']))
            
            # Update scope overview labels
            if hasattr(self, 'scope_overview_labels'):
                for widget in self.scope_overview_labels.values():
                    if hasattr(widget, 'configure'):
                        widget.configure(font=('Arial', self.fonts['normal']))
            
            # Update log text font
            if hasattr(self, 'log_text'):
                self.log_text.configure(font=('Consolas', self.fonts['normal']))
                
        except Exception as e:
            # Don't let font updates break the application
            print(f"Font update warning: {e}")

    def update_widget_dimensions(self):
        """Propagate dimension changes to registered widgets"""
        for scale in list(self.widget_registry['scales']):
            try:
                scale.configure(length=self.dimensions['scale_length'])
            except tk.TclError:
                self.widget_registry['scales'].remove(scale)
        for entry in list(self.widget_registry['entries']):
            try:
                entry.configure(width=self.dimensions['entry_width'])
            except tk.TclError:
                self.widget_registry['entries'].remove(entry)
        for combo in list(self.widget_registry['combos']):
            try:
                combo.configure(width=self.dimensions['combo_width'])
            except tk.TclError:
                self.widget_registry['combos'].remove(combo)
        for tree_entry in list(self.widget_registry['trees']):
            tree = tree_entry['widget']
            width_map = tree_entry.get('width_map') or {}
            try:
                for col in tree['columns']:
                    factor = width_map.get(col, 1.0)
                    target_width = int(self.dimensions['tree_column_width'] * factor)
                    tree.column(col, width=target_width)
            except tk.TclError:
                self.widget_registry['trees'].remove(tree_entry)

    def register_scale(self, widget):
        self.widget_registry['scales'].append(widget)

    def register_entry(self, widget):
        self.widget_registry['entries'].append(widget)

    def register_combo(self, widget):
        self.widget_registry['combos'].append(widget)

    def register_tree(self, widget, width_map=None):
        self.widget_registry['trees'].append({'widget': widget, 'width_map': width_map or {}})
    
    def on_window_resize(self, event):
        """Handle window resize events for scaling"""
        # Only handle root window resize events
        if event.widget != self.root:
            return
            
        # Calculate scale factor based on width change
        current_width = self.root.winfo_width()
        current_height = self.root.winfo_height()
        
        # Use the smaller scale factor to maintain proportions
        width_scale = current_width / self.initial_width
        height_scale = current_height / self.initial_height
        new_scale_factor = min(width_scale, height_scale)
        
        # Only update if scale factor changed significantly
        if abs(new_scale_factor - self.scale_factor) > 0.1:
            self.update_scaling(new_scale_factor)
    
    def setup_styles(self):
        """Setup dark theme styling with dynamic font support"""
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Initial font configuration
        self.update_font_styles()
    
    def update_font_styles(self):
        """Update all TTK styles with current font sizes"""
        # Configure colors and fonts for dark theme
        self.style.configure('TNotebook', 
                             background='#2b2b2b', 
                             borderwidth=0,
                             font=('Arial', self.fonts['normal']))
        
        self.style.configure('TNotebook.Tab', 
                             background='#404040', 
                             foreground='white',
                             padding=[int(20 * self.scale_factor), int(10 * self.scale_factor)],
                             font=('Arial', self.fonts['normal'], 'bold'))
        
        self.style.map('TNotebook.Tab', 
                        background=[('selected', '#555555')])
        
        self.style.configure('TFrame', background='#2b2b2b')
        
        self.style.configure('TLabel', 
                             background='#2b2b2b', 
                             foreground='white',
                             font=('Arial', self.fonts['normal']))
        
        self.style.configure('TButton', 
                             background='#404040', 
                             foreground='white',
                             font=('Arial', self.fonts['button']))
        
        self.style.map('TButton', 
                        background=[('active', '#555555')])
        
        self.style.configure('TCheckbutton',
                             background='#2b2b2b',
                             foreground='white',
                             font=('Arial', self.fonts['normal']))

        self.style.map('TCheckbutton',
                        background=[('active', '#3a3a3a')])

        self.style.configure('Heading.TLabel',
                             background='#2b2b2b',
                             foreground='white',
                             font=('Arial', self.fonts['heading'], 'bold'))
        
        self.style.configure('Title.TLabel',
                             background='#2b2b2b',
                             foreground='white',
                             font=('Arial', self.fonts['title'], 'bold'))

        # Section containers
        self.style.configure('Section.TLabelframe',
                             background='#2b2b2b',
                             foreground='#9CDCFE',
                             borderwidth=1,
                             relief='solid')

        self.style.configure('Section.TLabelframe.Label',
                             background='#2b2b2b',
                             foreground='#9CDCFE',
                             font=('Arial', self.fonts['heading'], 'bold'))

        self.style.configure('Subsection.TLabelframe',
                             background='#2b2b2b',
                             foreground='#D4D4D4',
                             borderwidth=1,
                             relief='solid')

        self.style.configure('Subsection.TLabelframe.Label',
                             background='#2b2b2b',
                             foreground='#D4D4D4',
                             font=('Arial', self.fonts['normal'], 'bold'))

        # Inputs
        self.style.configure('TEntry',
                             foreground='white',
                             fieldbackground='#1f1f1f',
                             insertcolor='white',
                             font=('Consolas', self.fonts['normal']))

        self.style.map('TEntry',
                        fieldbackground=[('readonly', '#1f1f1f')])

        self.style.configure('TCombobox',
                             foreground='white',
                             fieldbackground='#1f1f1f',
                             background='#1f1f1f',
                             font=('Consolas', self.fonts['normal']))

        self.style.map('TCombobox',
                        fieldbackground=[('readonly', '#1f1f1f')])

        self.style.configure('Horizontal.TScale',
                             background='#2b2b2b')

        # Custom styles for status indicators
        self.style.configure('Connected.TLabel', 
                             background='#2b2b2b', 
                             foreground='#4CAF50',
                             font=('Arial', self.fonts['status'], 'bold'))
        
        self.style.configure('Disconnected.TLabel', 
                             background='#2b2b2b', 
                             foreground='#F44336',
                             font=('Arial', self.fonts['status'], 'bold'))
        
        self.style.configure('Warning.TLabel', 
                             background='#2b2b2b', 
                             foreground='#FF9800',
                             font=('Arial', self.fonts['status'], 'bold'))
        
        self.style.configure('Warning.TButton',
                             background='#FF5722',
                             foreground='white',
                             font=('Arial', self.fonts['button'], 'bold'))

        # Treeview styling
        self.style.configure('Treeview',
                             background='#1f1f1f',
                             fieldbackground='#1f1f1f',
                             foreground='white',
                             rowheight=int(24 * self.scale_factor),
                             font=('Consolas', self.fonts['normal']))

        self.style.configure('Treeview.Heading',
                             background='#404040',
                             foreground='white',
                             font=('Arial', self.fonts['heading'], 'bold'))

        self.style.map('Treeview',
                        background=[('selected', '#264F78')],
                        foreground=[('selected', 'white')])
    
    def create_gui(self):
        """Create the main GUI interface"""
        # Main container
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Top control panel
        self.create_control_panel(main_frame)
        
        # Main notebook for tabs
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        
        # Create tabs
        self.create_overview_tab()
        self.create_power_supply_tab()
        self.create_electronic_load_tab()
        self.create_oscilloscope_tab()
        self.create_log_tab()
        self.create_diagnostics_tab()  # New diagnostics tab
        
        # Status bar
        self.create_status_bar(main_frame)
    
    def create_control_panel(self, parent):
        """Create the top control panel"""
        control_frame = ttk.Frame(parent)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Connection status
        status_frame = ttk.Frame(control_frame)
        status_frame.pack(side=tk.LEFT)
        
        self.connection_label = ttk.Label(status_frame, text="🔌 Pi Connection:", 
                                         style='Heading.TLabel')
        self.connection_label.pack(side=tk.LEFT, padx=(0, 5))
        
        self.connection_status = ttk.Label(status_frame, text="Disconnected", 
                                          style='Disconnected.TLabel')
        self.connection_status.pack(side=tk.LEFT, padx=(0, 20))
        
        # Control buttons
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(side=tk.LEFT)
        
        self.connect_btn = ttk.Button(button_frame, text="🔌 Connect to Pi", 
                                     command=self.connect_to_pi)
        self.connect_btn.pack(side=tk.LEFT, padx=5)
        
        self.discover_btn = ttk.Button(button_frame, text="🔍 Discover Instruments", 
                                      command=self.discover_instruments)
        self.discover_btn.pack(side=tk.LEFT, padx=5)
        
        self.refresh_btn = ttk.Button(button_frame, text="🔄 Auto Refresh", 
                                     command=self.toggle_auto_refresh)
        self.refresh_btn.pack(side=tk.LEFT, padx=5)
        
        # Emergency controls
        emergency_frame = ttk.Frame(control_frame)
        emergency_frame.pack(side=tk.RIGHT)
        
        self.emergency_btn = ttk.Button(emergency_frame, text="🚨 EMERGENCY STOP", 
                                       command=self.emergency_shutdown,
                                       style='Warning.TButton')
        self.emergency_btn.pack(side=tk.RIGHT, padx=5)
    
    def create_overview_tab(self):
        """Create the overview tab showing all instruments"""
        overview_frame = ttk.Frame(self.notebook)
        self.notebook.add(overview_frame, text="📊 Overview")
        
        # Create three columns for instruments
        instruments_frame = ttk.Frame(overview_frame)
        instruments_frame.pack(fill=tk.BOTH, expand=True,
                                padx=self.layout['outer_padx'],
                                pady=self.layout['outer_pady'])
        
        # Power Supply Overview
        ps_frame = ttk.LabelFrame(
            instruments_frame,
            text="⚡ DP832 Power Supply",
            padding=self.layout['section_pad'],
            style='Section.TLabelframe'
        )
        ps_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True,
                      padx=(0, self.layout['inner_pad']))
        
        self.ps_overview_labels = {}
        for ch in [1, 2, 3]:
            ch_frame = ttk.Frame(ps_frame)
            ch_frame.pack(fill=tk.X, pady=self.layout['inner_pad']//2)
            ch_frame.columnconfigure(1, weight=1)
            
            ch_label = ttk.Label(ch_frame, text=f"CH{ch}:", style='Heading.TLabel')
            ch_label.grid(row=0, column=0, sticky='w')
            
            self.ps_overview_labels[ch] = {
                'status': ttk.Label(ch_frame, text="🔴 OFF"),
                'voltage': ttk.Label(ch_frame, text="0.000V"),
                'current': ttk.Label(ch_frame, text="0.000A"),
                'power': ttk.Label(ch_frame, text="0.00W")
            }
            
            col_index = 1
            for label in self.ps_overview_labels[ch].values():
                label.grid(row=0, column=col_index, padx=self.layout['inner_pad']//2,
                           sticky='w')
                col_index += 1
            ch_frame.grid_columnconfigure(col_index - 1, weight=1)
        
        # Electronic Load Overview
        load_frame = ttk.LabelFrame(
            instruments_frame,
            text="⚖️ DL3000 Electronic Load",
            padding=self.layout['section_pad'],
            style='Section.TLabelframe'
        )
        load_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True,
                         padx=self.layout['inner_pad'])
        
        self.load_overview_labels = {
            'status': ttk.Label(load_frame, text="🔴 OFF"),
            'mode': ttk.Label(load_frame, text="Mode: CC"),
            'voltage': ttk.Label(load_frame, text="0.000V"),
            'current': ttk.Label(load_frame, text="0.000A"),
            'power': ttk.Label(load_frame, text="0.00W")
        }
        
        for label in self.load_overview_labels.values():
            label.pack(pady=self.layout['inner_pad']//2)
        
        # Oscilloscope Overview
        scope_frame = ttk.LabelFrame(
            instruments_frame,
            text="📊 DS1102E Oscilloscope",
            padding=self.layout['section_pad'],
            style='Section.TLabelframe'
        )
        scope_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True,
                         padx=(self.layout['inner_pad'], 0))
        
        self.scope_overview_labels = {
            'timebase': ttk.Label(scope_frame, text="Timebase: 1ms/div"),
            'trigger': ttk.Label(scope_frame, text="Trigger: CH1 @ 0V"),
            'ch1': ttk.Label(scope_frame, text="CH1: 🟢 1V/div"),
            'ch2': ttk.Label(scope_frame, text="CH2: 🔴 1V/div")
        }
        
        for label in self.scope_overview_labels.values():
            label.pack(pady=self.layout['inner_pad']//2)
        
        # Real-time plots
        self.create_overview_plots(overview_frame)
    
    def create_overview_plots(self, parent):
        """Create real-time measurement plots"""
        plot_frame = ttk.Frame(parent)
        plot_frame.pack(
            fill=tk.BOTH,
            expand=True,
            padx=self.layout['outer_padx'],
            pady=(0, self.layout['outer_pady'])
        )
        
        # Create matplotlib figure
        self.fig, ((self.ax1, self.ax2), (self.ax3, self.ax4)) = plt.subplots(2, 2, 
                                                                              figsize=(12, 6),
                                                                              facecolor='#2b2b2b')
        
        # Configure subplot appearance
        for ax in [self.ax1, self.ax2, self.ax3, self.ax4]:
            ax.set_facecolor('#404040')
            ax.tick_params(colors='white')
            ax.xaxis.label.set_color('white')
            ax.yaxis.label.set_color('white')
            ax.spines['bottom'].set_color('white')
            ax.spines['top'].set_color('white')
            ax.spines['right'].set_color('white')
            ax.spines['left'].set_color('white')
        
        self.ax1.set_title('Power Supply - Voltage', color='white')
        self.ax1.set_ylabel('Voltage (V)', color='white')
        
        self.ax2.set_title('Power Supply - Current', color='white')
        self.ax2.set_ylabel('Current (A)', color='white')
        
        self.ax3.set_title('Electronic Load', color='white')
        self.ax3.set_ylabel('Power (W)', color='white')
        
        self.ax4.set_title('System Overview', color='white')
        self.ax4.set_ylabel('Total Power (W)', color='white')
        
        # Embed in tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, plot_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Start animation
        self.animation = FuncAnimation(self.fig, self.update_plots, interval=1000, 
                                     blit=False, save_count=100, cache_frame_data=False)
    
    def create_power_supply_tab(self):
        """Create the power supply control tab"""
        ps_frame = ttk.Frame(self.notebook)
        self.notebook.add(ps_frame, text="⚡ Power Supply")
        
        # Instructions panel
        instructions = ttk.LabelFrame(
            ps_frame,
            text="💡 Power Supply Workflow",
            padding=self.layout['section_pad'],
            style='Section.TLabelframe'
        )
        instructions.pack(fill=tk.X,
                          padx=self.layout['outer_padx'],
                          pady=(self.layout['outer_pady'], self.layout['inner_pad']))
        
        instruction_text = ttk.Label(
            instructions,
            text="1️⃣ Set voltage and current limits  →  2️⃣ Click 'Set Values'  →  3️⃣ Turn 'Output ON'  →  4️⃣ Power available at terminals",
            style='TLabel',
            anchor=tk.CENTER,
            justify=tk.CENTER,
            wraplength=900
        )
        instruction_text.pack(fill=tk.X)
        
        # Control panel
        control_panel = ttk.LabelFrame(
            ps_frame,
            text="Control Panel",
            padding=self.layout['section_pad'],
            style='Section.TLabelframe'
        )
        control_panel.pack(fill=tk.X,
                           padx=self.layout['outer_padx'],
                           pady=(0, self.layout['outer_pady']))
        
        # Channel controls
        self.ps_controls = {}
        for ch in [1, 2, 3]:
            ch_frame = ttk.LabelFrame(
                control_panel,
                text=f"Channel {ch}",
                padding=self.layout['inner_pad'],
                style='Subsection.TLabelframe'
            )
            ch_frame.pack(fill=tk.X, pady=self.layout['inner_pad'])
            
            controls_row = ttk.Frame(ch_frame)
            controls_row.pack(fill=tk.X, expand=True)
            controls_row.columnconfigure(1, weight=1)
            controls_row.columnconfigure(4, weight=1)
            
            ttk.Label(controls_row, text="Voltage:").grid(row=0, column=0,
                                                           sticky='w',
                                                           padx=(0, self.layout['inner_pad']//2))
            voltage_var = tk.DoubleVar()
            voltage_scale = ttk.Scale(
                controls_row,
                from_=0,
                to=30.0 if ch != 3 else 5.0,
                variable=voltage_var,
                orient=tk.HORIZONTAL,
                length=self.dimensions['scale_length']
            )
            voltage_scale.grid(row=0, column=1, sticky='ew',
                               padx=(0, self.layout['inner_pad']//2))
            self.register_scale(voltage_scale)
            voltage_entry = ttk.Entry(
                controls_row,
                textvariable=voltage_var,
                width=self.dimensions['entry_width']
            )
            voltage_entry.grid(row=0, column=2, sticky='w',
                               padx=(0, self.layout['inner_pad']))
            self.register_entry(voltage_entry)
            
            ttk.Label(controls_row, text="Current:").grid(row=0, column=3,
                                                           sticky='w',
                                                           padx=(0, self.layout['inner_pad']//2))
            current_var = tk.DoubleVar()
            current_scale = ttk.Scale(
                controls_row,
                from_=0,
                to=3.0,
                variable=current_var,
                orient=tk.HORIZONTAL,
                length=self.dimensions['scale_length']
            )
            current_scale.grid(row=0, column=4, sticky='ew',
                               padx=(0, self.layout['inner_pad']//2))
            self.register_scale(current_scale)
            current_entry = ttk.Entry(
                controls_row,
                textvariable=current_var,
                width=self.dimensions['entry_width']
            )
            current_entry.grid(row=0, column=5, sticky='w',
                               padx=(0, self.layout['inner_pad']))
            self.register_entry(current_entry)
            
            output_var = tk.BooleanVar()
            output_btn = ttk.Checkbutton(
                controls_row,
                text="Output ON",
                variable=output_var,
                command=lambda c=ch: self.toggle_ps_output(c)
            )
            output_btn.grid(row=0, column=6, sticky='w',
                            padx=(0, self.layout['inner_pad']))
            output_btn.configure(width=12)
            
            set_btn = ttk.Button(
                controls_row,
                text="📝 Set V & I Limits",
                command=lambda c=ch: self.set_ps_values(c)
            )
            set_btn.grid(row=0, column=7, sticky='e')
            set_btn.configure(width=18)
            
            self.ps_controls[ch] = {
                'voltage_var': voltage_var,
                'current_var': current_var,
                'output_var': output_var,
                'voltage_scale': voltage_scale,
                'current_scale': current_scale,
                'voltage_entry': voltage_entry,
                'current_entry': current_entry,
                'output_button': output_btn,
                'set_button': set_btn
            }
        
        # Status display
        status_panel = ttk.LabelFrame(
            ps_frame,
            text="Real-time Status",
            padding=self.layout['section_pad'],
            style='Section.TLabelframe'
        )
        status_panel.pack(fill=tk.BOTH, expand=True,
                           padx=self.layout['outer_padx'],
                           pady=(0, self.layout['outer_pady']))
        
        # Create status table
        self.create_ps_status_table(status_panel)
    
    def create_ps_status_table(self, parent):
        """Create power supply status table"""
        # Treeview for status display
        columns = ('Channel', 'Output', 'Set V', 'Meas V', 'Set I', 'Meas I', 'Power')
        self.ps_tree = ttk.Treeview(parent, columns=columns, show='headings', height=6)

        width_factors = {
            'Channel': 0.9,
            'Output': 1.0,
            'Set V': 1.1,
            'Meas V': 1.1,
            'Set I': 1.1,
            'Meas I': 1.1,
            'Power': 1.1
        }
        
        for col in columns:
            self.ps_tree.heading(col, text=col)
            width = int(self.dimensions['tree_column_width'] * width_factors.get(col, 1.0))
            self.ps_tree.column(col, width=width, anchor=tk.CENTER, stretch=True)
        
        self.ps_tree.pack(fill=tk.BOTH, expand=True)
        self.register_tree(self.ps_tree, width_factors)
        
        # Populate initial data
        for ch in [1, 2, 3]:
            self.ps_tree.insert('', 'end', iid=f'ch{ch}',
                               values=(f'CH{ch}', 'OFF', '0.000V', '0.000V', 
                                      '0.000A', '0.000A', '0.00W'))
    
    def create_electronic_load_tab(self):
        """Create the electronic load control tab"""
        load_frame = ttk.Frame(self.notebook)
        self.notebook.add(load_frame, text="⚖️ Electronic Load")
        
        # Control panel
        control_panel = ttk.LabelFrame(
            load_frame,
            text="Control Panel",
            padding=self.layout['section_pad'],
            style='Section.TLabelframe'
        )
        control_panel.pack(fill=tk.X,
                           padx=self.layout['outer_padx'],
                           pady=(self.layout['outer_pady'], self.layout['outer_pady']))
        
        # Mode selection
        mode_frame = ttk.Frame(control_panel)
        mode_frame.pack(fill=tk.X, pady=self.layout['inner_pad'])
        mode_frame.columnconfigure(2, weight=1)
        
        mode_label = ttk.Label(mode_frame, text="Operation Mode:", style='Heading.TLabel')
        mode_label.grid(row=0, column=0, sticky='w')
        
        self.load_mode_var = tk.StringVar(value="CC")
        mode_combo = ttk.Combobox(
            mode_frame,
            textvariable=self.load_mode_var,
            values=["CC", "CV", "CP", "CR"],
            state="readonly",
            width=self.dimensions['combo_width']
        )
        mode_combo.grid(row=0, column=1, sticky='w', padx=(self.layout['inner_pad'], 0))
        self.register_combo(mode_combo)
        mode_combo.bind('<<ComboboxSelected>>', self.on_load_mode_change)
        
        self.load_input_var = tk.BooleanVar()
        input_btn = ttk.Checkbutton(
            mode_frame,
            text="Input ENABLED",
            variable=self.load_input_var,
            command=self.toggle_load_input
        )
        input_btn.grid(row=0, column=2, sticky='w', padx=(self.layout['inner_pad'], 0))
        input_btn.configure(width=16)
        
        # Parameter controls
        params_frame = ttk.Frame(control_panel)
        params_frame.pack(fill=tk.X, pady=(0, self.layout['inner_pad']))
        params_frame.columnconfigure(0, weight=1)
        
        self.load_controls = {}
        
        # Current control
        self.create_load_parameter_control(params_frame, "Current (A):", "current", 0, 21, 0)
        
        # Voltage control
        self.create_load_parameter_control(params_frame, "Voltage (V):", "voltage", 0, 150, 1)
        
        # Power control
        self.create_load_parameter_control(params_frame, "Power (W):", "power", 0, 200, 2)
        
        # Resistance control
        self.create_load_parameter_control(params_frame, "Resistance (Ω):", "resistance", 0.02, 40000, 3)
    
    def create_load_parameter_control(self, parent, label_text, param_name, min_val, max_val, row):
        """Create a parameter control for the electronic load"""
        param_frame = ttk.Frame(parent)
        param_frame.grid(row=row, column=0, sticky='ew', pady=self.layout['inner_pad']//2)
        param_frame.columnconfigure(1, weight=1)
        
        ttk.Label(param_frame, text=label_text, width=15).grid(row=0, column=0, sticky='w')
        
        var = tk.DoubleVar()
        scale = ttk.Scale(
            param_frame,
            from_=min_val,
            to=max_val,
            variable=var,
            orient=tk.HORIZONTAL,
            length=self.dimensions['scale_length']
        )
        scale.grid(row=0, column=1, sticky='ew', padx=(self.layout['inner_pad']//2, self.layout['inner_pad']//2))
        self.register_scale(scale)
        
        entry = ttk.Entry(param_frame, textvariable=var, width=self.dimensions['entry_width'])
        entry.grid(row=0, column=2, sticky='w')
        self.register_entry(entry)
        
        set_btn = ttk.Button(
            param_frame,
            text="Apply",
            command=lambda: self.set_load_parameter(param_name)
        )
        set_btn.grid(row=0, column=3, sticky='e', padx=(self.layout['inner_pad']//2, 0))
        set_btn.configure(width=10)
        
        self.load_controls[param_name] = {'var': var, 'scale': scale, 'entry': entry}
    
    def create_oscilloscope_tab(self):
        """Create the oscilloscope control tab"""
        scope_frame = ttk.Frame(self.notebook)
        self.notebook.add(scope_frame, text="📊 Oscilloscope")
        
        # Control panel
        control_panel = ttk.LabelFrame(
            scope_frame,
            text="Control Panel",
            padding=self.layout['section_pad'],
            style='Section.TLabelframe'
        )
        control_panel.pack(fill=tk.X,
                           padx=self.layout['outer_padx'],
                           pady=(self.layout['outer_pady'], self.layout['inner_pad']))
        
        # Timebase and trigger controls
        tb_frame = ttk.Frame(control_panel)
        tb_frame.pack(fill=tk.X, pady=self.layout['inner_pad'])
        tb_frame.columnconfigure(1, weight=1)
        tb_frame.columnconfigure(2, weight=0)
        tb_frame.columnconfigure(3, weight=0)
        
        ttk.Label(tb_frame, text="Timebase (s/div):", width=16).grid(row=0, column=0, sticky='w')
        self.timebase_var = tk.StringVar(value="1e-3")
        timebase_combo = ttk.Combobox(
            tb_frame,
            textvariable=self.timebase_var,
            values=["1e-6", "5e-6", "1e-5", "5e-5", "1e-4", "5e-4", "1e-3", "5e-3", "1e-2", "5e-2"],
            width=self.dimensions['combo_width']
        )
        timebase_combo.grid(row=0, column=1, sticky='w')
        self.register_combo(timebase_combo)
        
        set_tb_btn = ttk.Button(tb_frame, text="Set Timebase", command=self.set_timebase)
        set_tb_btn.grid(row=0, column=2, sticky='w', padx=(self.layout['inner_pad'], 0))
        set_tb_btn.configure(width=14)
        
        auto_btn = ttk.Button(tb_frame, text="Auto Setup", command=self.scope_auto_setup)
        auto_btn.grid(row=0, column=3, sticky='w', padx=(self.layout['inner_pad'], 0))
        auto_btn.configure(width=12)
        
        # Screen capture controls
        capture_frame = ttk.Frame(control_panel)
        capture_frame.pack(fill=tk.X, pady=self.layout['inner_pad'])
        capture_frame.columnconfigure(3, weight=1)
        
        capture_btn = ttk.Button(
            capture_frame,
            text="📸 HARDcopy Capture",
            command=self.capture_scope_screen,
            style='TButton'
        )
        capture_btn.grid(row=0, column=0, sticky='w')
        capture_btn.configure(width=22)
        
        refresh_btn = ttk.Button(
            capture_frame,
            text="🔄 Refresh Display",
            command=self.refresh_scope_display
        )
        refresh_btn.grid(row=0, column=1, sticky='w', padx=(self.layout['inner_pad'], 0))
        refresh_btn.configure(width=18)
        
        test_btn = ttk.Button(
            capture_frame,
            text="🧪 Test Mode",
            command=self.test_scope_capture,
            style='TButton'
        )
        test_btn.grid(row=0, column=2, sticky='w', padx=(self.layout['inner_pad'], 0))
        test_btn.configure(width=14)
        
        self.capture_status = ttk.Label(
            capture_frame,
            text="Ready for HARDcopy",
            style='TLabel'
        )
        self.capture_status.grid(row=0, column=3, sticky='e')
        
        # Channel controls
        ch_frame = ttk.Frame(control_panel)
        ch_frame.pack(fill=tk.X, pady=self.layout['inner_pad'])
        
        self.scope_controls = {}
        for ch in [1, 2]:
            ch_control_frame = ttk.LabelFrame(
                ch_frame,
                text=f"Channel {ch}",
                padding=self.layout['inner_pad'],
                style='Subsection.TLabelframe'
            )
            ch_control_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True,
                                   padx=(0, self.layout['inner_pad']) if ch == 1 else (self.layout['inner_pad'], 0))
            
            enabled_var = tk.BooleanVar(value=ch == 1)
            enable_btn = ttk.Checkbutton(
                ch_control_frame,
                text="Enabled",
                variable=enabled_var,
                command=lambda c=ch: self.toggle_scope_channel(c)
            )
            enable_btn.pack(anchor='w')
            enable_btn.configure(width=12)
            
            scale_frame = ttk.Frame(ch_control_frame)
            scale_frame.pack(fill=tk.X, pady=self.layout['inner_pad']//2)
            ttk.Label(scale_frame, text="V/div:").pack(side=tk.LEFT)
            scale_var = tk.StringVar(value="1.0")
            scale_combo = ttk.Combobox(
                scale_frame,
                textvariable=scale_var,
                values=["0.001", "0.002", "0.005", "0.01", "0.02", "0.05", "0.1", "0.2", "0.5", "1.0", "2.0", "5.0"],
                width=self.dimensions['combo_width']
            )
            scale_combo.pack(side=tk.LEFT, padx=(self.layout['inner_pad']//2, 0))
            self.register_combo(scale_combo)
            
            self.scope_controls[ch] = {
                'enabled_var': enabled_var,
                'scale_var': scale_var
            }
        
        # Waveform display with matplotlib
        waveform_frame = ttk.LabelFrame(
            scope_frame,
            text="Oscilloscope Screen Capture",
            padding=self.layout['section_pad'],
            style='Section.TLabelframe'
        )
        waveform_frame.pack(fill=tk.BOTH, expand=True,
                             padx=self.layout['outer_padx'],
                             pady=(0, self.layout['outer_pady']))
        
        # Create oscilloscope screen display
        self.create_oscilloscope_display(waveform_frame)
    
    def create_oscilloscope_display(self, parent):
        """Create oscilloscope screen capture display"""
        # Create frame for image display
        self.scope_display_frame = ttk.Frame(parent)
        self.scope_display_frame.pack(fill=tk.BOTH, expand=True)
        
        # Initial message label
        self.scope_image_label = ttk.Label(self.scope_display_frame, 
                                          text="📸 Click 'Capture Screen' to take a screenshot\nfrom the DS1102E oscilloscope",
                                          style='Heading.TLabel',
                                          anchor=tk.CENTER,
                                          justify=tk.CENTER)
        self.scope_image_label.pack(expand=True, fill=tk.BOTH)
        
        # Store current image path
        self.current_scope_image = None
    
    def capture_scope_screen(self):
        """Capture screenshot from DS1102E using :HARDcopy command"""
        if not self.connected:
            messagebox.showwarning("Warning", "Please connect to Pi first")
            return
            
        resource = self.instruments['oscilloscope']['resource']
        if not resource:
            messagebox.showwarning("Warning", "Oscilloscope not connected")
            return
        
        def capture_thread():
            try:
                self.root.after(0, lambda: self.capture_status.configure(
                    text="📸 HARDcopy capture...", style='Warning.TLabel'))
                
                self.add_log("📸 DS1102E HARDcopy screen capture starting...")
                self.add_log("ℹ️  This will save HardCopyxxx.bmp to USB device")
                
                # DS1102E HARDcopy method - saves to USB device
                capture_cmd = f"""
cd ~/rigol
source venv/bin/activate

python << 'EOF'
import time
import os
import glob

print("DS1102E HARDcopy Process Starting...")

try:
    with open('{resource}', 'w+b', buffering=0) as f:
        print("Connection opened successfully")
        
        # Clear any pending data
        try:
            f.read(1024)
        except:
            pass
        
        # Send the HARDcopy command
        print("Sending :HARDcopy command...")
        f.write(b':HARDcopy\\n')
        f.flush()
        
        print("HARDcopy command sent, waiting for scope to process...")
        # Give the scope time to process the command and save to USB
        time.sleep(5.0)  
        
        # Check for any response/error
        try:
            response = f.read(1024)
            if response:
                response_text = response.decode(errors='ignore').strip()
                if response_text:
                    if 'error' in response_text.lower():
                        print(f"SCOPE_ERROR:{{response_text}}")
                    else:
                        print(f"SCOPE_RESPONSE:{{response_text}}")
        except:
            pass  # No response is normal for HARDcopy
        
        print("HARDCOPY_COMMAND_COMPLETE")

except Exception as e:
    print(f"ERROR:{{str(e)}}")
    import traceback
    traceback.print_exc()

# Now we need to find the created HardCopyxxx.bmp file
# The DS1102E saves to USB device, which might be mounted on the Pi
print("\\nSearching for HardCopy files...")

# Check common USB mount points on the Pi
usb_mount_points = [
    '/media/usb*',
    '/mnt/usb*', 
    '/media/morgan/*',
    '/mnt/*',
    '/media/*'
]

hardcopy_files = []

for mount_pattern in usb_mount_points:
    try:
        mount_dirs = glob.glob(mount_pattern)
        for mount_dir in mount_dirs:
            if os.path.isdir(mount_dir):
                print(f"Checking mount point: {{mount_dir}}")
                hardcopy_pattern = os.path.join(mount_dir, 'HardCopy*.bmp')
                files = glob.glob(hardcopy_pattern)
                if files:
                    hardcopy_files.extend(files)
                    for file in files:
                        print(f"FOUND_HARDCOPY:{{file}}")
    except Exception as search_err:
        print(f"Search error in {{mount_pattern}}: {{search_err}}")

# Also check the current directory in case the scope saved locally
local_hardcopy = glob.glob('HardCopy*.bmp')
if local_hardcopy:
    hardcopy_files.extend(local_hardcopy) 
    for file in local_hardcopy:
        print(f"FOUND_LOCAL_HARDCOPY:{{file}}")

if hardcopy_files:
    # Get the most recent file
    newest_file = max(hardcopy_files, key=os.path.getmtime)
    file_size = os.path.getsize(newest_file)
    print(f"SUCCESS_HARDCOPY:{{newest_file}}:{{file_size}} bytes")
    
    # Copy to our working directory for easier transfer
    import shutil
    local_copy = os.path.basename(newest_file)
    shutil.copy2(newest_file, local_copy)
    print(f"COPIED_TO:{{local_copy}}")
else:
    print("NO_HARDCOPY_FILES_FOUND")
    print("Note: Make sure USB device is connected to oscilloscope")
    print("The DS1102E saves HardCopy files to USB, not internal memory")

EOF
"""
                
                self.add_log("🔄 Executing HARDcopy command...")
                result = send_command(self.ssh_connection, capture_cmd, timeout=60)
                
                if result and "SUCCESS_HARDCOPY:" in result:
                    # Parse the saved image info
                    success_lines = [line for line in result.split('\n') if 'SUCCESS_HARDCOPY:' in line]
                    if success_lines:
                        success_info = success_lines[0].split('SUCCESS_HARDCOPY:')[1]
                        original_file = success_info.split(':')[0]
                        file_size = success_info.split(':')[1]
                        
                        # Look for the copied file name
                        copied_lines = [line for line in result.split('\n') if 'COPIED_TO:' in line]
                        if copied_lines:
                            filename = copied_lines[0].split('COPIED_TO:')[1]
                            self.add_log(f"✅ HardCopy captured: {filename} ({file_size})")
                            
                            # Transfer the file
                            self.transfer_hardcopy_image(filename)
                        else:
                            self.add_log(f"✅ HardCopy found but copy failed")
                            self.root.after(0, lambda: self.capture_status.configure(
                                text="⚠️  Found but not copied", style='Warning.TLabel'))
                    
                elif result and "FOUND_HARDCOPY:" in result:
                    # Files found but no success message
                    found_lines = [line for line in result.split('\n') if 'FOUND_HARDCOPY:' in line]
                    self.add_log(f"✅ Found {len(found_lines)} HardCopy files")
                    for line in found_lines:
                        filename = line.split('FOUND_HARDCOPY:')[1]
                        self.add_log(f"   📁 {filename}")
                    
                    self.root.after(0, lambda: self.capture_status.configure(
                        text="✅ Files found", style='Connected.TLabel'))
                    
                elif result and "NO_HARDCOPY_FILES_FOUND" in result:
                    self.add_log("❌ No HardCopy files found")
                    self.add_log("💡 Make sure USB device is connected to DS1102E")
                    self.add_log("💡 DS1102E saves to USB, not internal memory")
                    self.root.after(0, lambda: self.capture_status.configure(
                        text="❌ No USB files", style='Disconnected.TLabel'))
                    
                elif result and "SCOPE_ERROR:" in result:
                    error_info = result.split("SCOPE_ERROR:")[1].split('\n')[0]
                    self.add_log(f"❌ Oscilloscope error: {error_info}")
                    self.root.after(0, lambda: self.capture_status.configure(
                        text="❌ Scope error", style='Disconnected.TLabel'))
                        
                else:
                    # Check for command completion at least
                    if result and "HARDCOPY_COMMAND_COMPLETE" in result:
                        self.add_log("✅ HARDcopy command sent successfully")
                        self.add_log("💡 Check USB device on oscilloscope for HardCopyxxx.bmp")
                        self.root.after(0, lambda: self.capture_status.configure(
                            text="✅ Command sent", style='Connected.TLabel'))
                    else:
                        error_info = "Unknown error"
                        if result and "ERROR:" in result:
                            error_info = result.split("ERROR:")[1].strip()
                        
                        self.add_log(f"❌ HARDcopy failed: {error_info}")
                        self.root.after(0, lambda: self.capture_status.configure(
                            text="❌ Command failed", style='Disconnected.TLabel'))
                    
            except Exception as e:
                self.add_log(f"❌ HARDcopy capture error: {e}")
                self.root.after(0, lambda: self.capture_status.configure(
                    text="❌ Error occurred", style='Disconnected.TLabel'))
        
        threading.Thread(target=capture_thread, daemon=True).start()
    
    def transfer_hardcopy_image(self, filename):
        """Transfer HardCopy image from Pi to local machine"""
        try:
            import paramiko
            from datetime import datetime
            
            # Create local directory
            local_images_dir = os.path.join(os.path.dirname(__file__), "scope_captures")
            os.makedirs(local_images_dir, exist_ok=True)
            
            # Generate local filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            local_filename = os.path.join(local_images_dir, f"hardcopy_{timestamp}.bmp")
            
            # Transfer via SFTP
            sftp = self.ssh_connection.open_sftp()
            remote_path = f"/home/morgan/rigol/{filename}"
            
            sftp.get(remote_path, local_filename)
            sftp.close()
            
            # Display the image
            self.display_scope_image(local_filename)
            
            self.add_log(f"✅ HardCopy image transferred: {os.path.basename(local_filename)}")
            self.root.after(0, lambda: self.capture_status.configure(
                text="✅ HARDcopy complete", style='Connected.TLabel'))
            
        except Exception as e:
            self.add_log(f"❌ HardCopy transfer failed: {e}")
            self.root.after(0, lambda: self.capture_status.configure(
                text="❌ Transfer failed", style='Disconnected.TLabel'))
    
    def display_scope_image(self, image_path):
        """Display the captured oscilloscope image in the GUI"""
        try:
            from PIL import Image, ImageTk
            
            # Load and resize image to fit display
            image = Image.open(image_path)
            
            # Calculate display size (maintain aspect ratio)
            display_width = 800
            display_height = 600
            
            # Get image dimensions
            img_width, img_height = image.size
            
            # Calculate scaling factor
            scale_x = display_width / img_width
            scale_y = display_height / img_height
            scale = min(scale_x, scale_y)
            
            # Resize image
            new_width = int(img_width * scale)
            new_height = int(img_height * scale)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Convert to PhotoImage
            photo = ImageTk.PhotoImage(image)
            
            # Update label to display image
            self.scope_image_label.configure(image=photo, text="")
            self.scope_image_label.image = photo  # Keep reference
            
            # Store current image path
            self.current_scope_image = image_path
            
            self.add_log(f"📊 Displaying oscilloscope screen capture")
            
        except Exception as e:
            self.add_log(f"❌ Image display error: {e}")
            # Show error message in label
            self.scope_image_label.configure(
                text=f"❌ Failed to display image\n{str(e)}", 
                image="")
    
    def refresh_scope_display(self):
        """Refresh the current scope display"""
        if self.current_scope_image and os.path.exists(self.current_scope_image):
            self.display_scope_image(self.current_scope_image)
            self.add_log("🔄 Scope display refreshed")
        else:
            self.capture_scope_screen()
    
    def test_scope_capture(self):
        """Test mode for screen capture functionality"""
        self.add_log("🧪 Running test mode for screen capture...")
        
        def test_thread():
            try:
                self.root.after(0, lambda: self.capture_status.configure(
                    text="🧪 Creating test image...", style='Warning.TLabel'))
                
                # Create a test BMP image
                import numpy as np
                from PIL import Image, ImageDraw, ImageFont
                
                # Create a test oscilloscope-like image
                width, height = 800, 600
                image = Image.new('RGB', (width, height), color='black')
                draw = ImageDraw.Draw(image)
                
                # Draw grid like an oscilloscope
                grid_color = (0, 64, 0)  # Dark green
                for x in range(0, width, 80):
                    draw.line([(x, 0), (x, height)], fill=grid_color, width=1)
                for y in range(0, height, 60):
                    draw.line([(0, y), (width, y)], fill=grid_color, width=1)
                
                # Draw some test waveforms
                import math
                waveform_color = (0, 255, 0)  # Bright green
                
                # Channel 1: Sine wave
                points = []
                for x in range(width):
                    y = height/2 + 100 * math.sin(2 * math.pi * x / 100)
                    points.append((x, int(y)))
                
                for i in range(len(points) - 1):
                    draw.line([points[i], points[i+1]], fill=waveform_color, width=2)
                
                # Channel 2: Square wave  
                square_color = (255, 64, 64)  # Red
                y_base = height/2
                for x in range(0, width, 50):
                    y_val = y_base + (50 if (x // 50) % 2 == 0 else -50)
                    if x < width - 50:
                        draw.rectangle([x, y_val-2, x+50, y_val+2], fill=square_color)
                
                # Add some text
                try:
                    # Try to use default font
                    draw.text((10, 10), "TEST MODE - RIGOL DS1102E", fill=(255, 255, 255))
                    draw.text((10, 30), f"Captured: {time.strftime('%Y-%m-%d %H:%M:%S')}", 
                             fill=(192, 192, 192))
                    draw.text((10, height-30), "CH1: 2V/div  CH2: 1V/div  Time: 1ms/div", 
                             fill=(192, 192, 192))
                except:
                    pass
                
                # Save test image
                local_images_dir = os.path.join(os.path.dirname(__file__), "scope_captures")
                os.makedirs(local_images_dir, exist_ok=True)
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                test_filename = os.path.join(local_images_dir, f"test_capture_{timestamp}.bmp")
                
                image.save(test_filename, 'BMP')
                
                # Display the test image
                self.display_scope_image(test_filename)
                
                self.add_log(f"✅ Test image created and displayed: {os.path.basename(test_filename)}")
                self.root.after(0, lambda: self.capture_status.configure(
                    text="✅ Test complete", style='Connected.TLabel'))
                
            except Exception as e:
                self.add_log(f"❌ Test mode error: {e}")
                self.root.after(0, lambda: self.capture_status.configure(
                    text="❌ Test failed", style='Disconnected.TLabel'))
        
        threading.Thread(target=test_thread, daemon=True).start()
    
    def create_log_tab(self):
        """Create the log/console tab"""
        log_frame = ttk.Frame(self.notebook)
        self.notebook.add(log_frame, text="📝 Log")
        
        # Log display
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            bg='#1e1e1e',
            fg='white',
            insertbackground='white',
            font=('Consolas', self.fonts['normal'])
        )
        self.log_text.pack(fill=tk.BOTH, expand=True,
                           padx=self.layout['outer_padx'],
                           pady=self.layout['outer_pady'])
        
        # Add initial log message
        self.add_log("🚀 Rigol Multi-Instrument Control System - GUI Version Started")
        self.add_log("Ready to connect to Raspberry Pi...")
    
    def create_diagnostics_tab(self):
        """Create the diagnostics tab for command verification and system status"""
        diag_frame = ttk.Frame(self.notebook)
        self.notebook.add(diag_frame, text="🔧 Diagnostics")
        
        # Command statistics panel
        stats_panel = ttk.LabelFrame(
            diag_frame,
            text="Command Verification Statistics",
            padding=self.layout['section_pad'],
            style='Section.TLabelframe'
        )
        stats_panel.pack(fill=tk.X,
                          padx=self.layout['outer_padx'],
                          pady=(self.layout['outer_pady'], self.layout['inner_pad']))
        
        # Stats display
        stats_grid = ttk.Frame(stats_panel)
        stats_grid.pack(fill=tk.X, pady=(0, self.layout['inner_pad']))
        stats_grid.columnconfigure(1, weight=1)
        stats_grid.columnconfigure(3, weight=1)
        
        # Create statistics labels
        total_label = ttk.Label(stats_grid, text="Total Commands:", style='TLabel')
        total_label.grid(row=0, column=0, sticky=tk.W,
                         padx=(0, self.layout['inner_pad']//2))
        self.stats_total = ttk.Label(stats_grid, text="0", style='TLabel')
        self.stats_total.grid(row=0, column=1, sticky=tk.W)
        
        success_label = ttk.Label(stats_grid, text="Successful:", style='TLabel')
        success_label.grid(row=0, column=2, sticky=tk.W,
                           padx=(self.layout['inner_pad'], self.layout['inner_pad']//2))
        self.stats_success = ttk.Label(stats_grid, text="0", style='Connected.TLabel')
        self.stats_success.grid(row=0, column=3, sticky=tk.W)
        
        failed_label = ttk.Label(stats_grid, text="Failed:", style='TLabel')
        failed_label.grid(row=1, column=0, sticky=tk.W,
                          padx=(0, self.layout['inner_pad']//2))
        self.stats_failed = ttk.Label(stats_grid, text="0", style='Disconnected.TLabel')
        self.stats_failed.grid(row=1, column=1, sticky=tk.W)
        
        rate_label = ttk.Label(stats_grid, text="Success Rate:", style='TLabel')
        rate_label.grid(row=1, column=2, sticky=tk.W,
                         padx=(self.layout['inner_pad'], self.layout['inner_pad']//2))
        self.stats_rate = ttk.Label(stats_grid, text="0%", style='TLabel')
        self.stats_rate.grid(row=1, column=3, sticky=tk.W)
        
        attempts_label = ttk.Label(stats_grid, text="Avg Attempts:", style='TLabel')
        attempts_label.grid(row=2, column=0, sticky=tk.W,
                             padx=(0, self.layout['inner_pad']//2))
        self.stats_attempts = ttk.Label(stats_grid, text="0", style='TLabel')
        self.stats_attempts.grid(row=2, column=1, sticky=tk.W)
        
        # Timeout settings
        timeout_frame = ttk.Frame(stats_panel)
        timeout_frame.pack(fill=tk.X, pady=self.layout['inner_pad']//2)
        timeout_frame.columnconfigure(1, weight=1)
        
        timeout_label = ttk.Label(timeout_frame, text="Command Timeout (s):", style='TLabel')
        timeout_label.grid(row=0, column=0, sticky='w')
        self.timeout_var = tk.DoubleVar(value=self.command_timeout)
        timeout_scale = ttk.Scale(
            timeout_frame,
            from_=1.0,
            to=10.0,
            variable=self.timeout_var,
            orient=tk.HORIZONTAL,
            length=self.dimensions['scale_length']
        )
        timeout_scale.grid(row=0, column=1, sticky='ew', padx=(self.layout['inner_pad']//2, self.layout['inner_pad']//2))
        self.register_scale(timeout_scale)
        
        timeout_entry = ttk.Entry(timeout_frame, textvariable=self.timeout_var, width=self.dimensions['entry_width'])
        timeout_entry.grid(row=0, column=2, sticky='w')
        self.register_entry(timeout_entry)
        
        timeout_btn = ttk.Button(timeout_frame, text="Apply", command=self.update_timeout)
        timeout_btn.grid(row=0, column=3, sticky='e', padx=(self.layout['inner_pad']//2, 0))
        timeout_btn.configure(width=10)
        
        # Max retries setting
        retry_frame = ttk.Frame(stats_panel)
        retry_frame.pack(fill=tk.X, pady=self.layout['inner_pad']//2)
        retry_frame.columnconfigure(1, weight=1)
        
        retries_label = ttk.Label(retry_frame, text="Max Retries:", style='TLabel')
        retries_label.grid(row=0, column=0, sticky='w')
        self.retry_var = tk.IntVar(value=self.max_retries)
        retry_scale = ttk.Scale(
            retry_frame,
            from_=1,
            to=10,
            variable=self.retry_var,
            orient=tk.HORIZONTAL,
            length=self.dimensions['scale_length']
        )
        retry_scale.grid(row=0, column=1, sticky='ew', padx=(self.layout['inner_pad']//2, self.layout['inner_pad']//2))
        self.register_scale(retry_scale)
        
        retry_entry = ttk.Entry(retry_frame, textvariable=self.retry_var, width=self.dimensions['entry_width'])
        retry_entry.grid(row=0, column=2, sticky='w')
        self.register_entry(retry_entry)
        
        retry_btn = ttk.Button(retry_frame, text="Apply", command=self.update_retries)
        retry_btn.grid(row=0, column=3, sticky='e', padx=(self.layout['inner_pad']//2, 0))
        retry_btn.configure(width=10)
        
        # Failed commands panel
        failed_panel = ttk.LabelFrame(
            diag_frame,
            text="Recent Failed Commands",
            padding=self.layout['section_pad'],
            style='Section.TLabelframe'
        )
        failed_panel.pack(fill=tk.BOTH, expand=True,
                          padx=self.layout['outer_padx'],
                          pady=(0, self.layout['outer_pady']))
        
        # Treeview for failed commands
        columns = ('Time', 'Resource', 'Command', 'Error', 'Attempts')
        self.failed_tree = ttk.Treeview(failed_panel, columns=columns, show='headings', height=8)
        
        for col in columns:
            self.failed_tree.heading(col, text=col)
            
        # Column widths
        failed_widths = {
            'Time': 1.0,
            'Resource': 1.1,
            'Command': 1.6,
            'Error': 1.8,
            'Attempts': 0.9
        }
        for col, factor in failed_widths.items():
            self.failed_tree.column(col, width=int(self.dimensions['tree_column_width'] * factor))
        
        # Scrollbar
        failed_scroll = ttk.Scrollbar(failed_panel, orient=tk.VERTICAL, command=self.failed_tree.yview)
        self.failed_tree.configure(yscrollcommand=failed_scroll.set)
        
        self.failed_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        failed_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.register_tree(self.failed_tree, failed_widths)
        
        # Control buttons
        control_frame = ttk.Frame(diag_frame)
        control_frame.pack(fill=tk.X,
                           padx=self.layout['outer_padx'],
                           pady=(0, self.layout['outer_pady']))
        
        refresh_btn = ttk.Button(control_frame, text="🔄 Refresh Stats", command=self.refresh_diagnostics)
        refresh_btn.pack(side=tk.LEFT, padx=(0, self.layout['inner_pad']//2))
        refresh_btn.configure(width=16)
        
        clear_btn = ttk.Button(control_frame, text="🗑️ Clear History", command=self.clear_command_history)
        clear_btn.pack(side=tk.LEFT, padx=(0, self.layout['inner_pad']//2))
        clear_btn.configure(width=16)
        
        export_btn = ttk.Button(control_frame, text="📊 Export Stats", command=self.export_statistics)
        export_btn.pack(side=tk.LEFT, padx=(0, self.layout['inner_pad']//2))
        export_btn.configure(width=16)
        
        # Start periodic refresh
        self.refresh_diagnostics()
    
    def update_timeout(self):
        """Update command timeout setting"""
        self.command_timeout = self.timeout_var.get()
        self.add_log(f"⚙️ Command timeout updated: {self.command_timeout}s")
    
    def update_retries(self):
        """Update max retries setting"""
        self.max_retries = int(self.retry_var.get())
        self.add_log(f"⚙️ Max retries updated: {self.max_retries}")
    
    def refresh_diagnostics(self):
        """Refresh diagnostics display"""
        stats = self.get_command_statistics()
        
        # Update stats labels
        self.stats_total.configure(text=str(stats['total']))
        self.stats_success.configure(text=str(stats['successful']))
        self.stats_failed.configure(text=str(stats['failed']))
        self.stats_rate.configure(text=f"{stats['success_rate']:.1f}%")
        self.stats_attempts.configure(text=f"{stats['avg_attempts']:.1f}")
        
        # Color code success rate
        if stats['success_rate'] >= 95:
            self.stats_rate.configure(style='Connected.TLabel')
        elif stats['success_rate'] >= 80:
            self.stats_rate.configure(style='Warning.TLabel')
        else:
            self.stats_rate.configure(style='Disconnected.TLabel')
        
        # Update failed commands list (show last 50)
        self.failed_tree.delete(*self.failed_tree.get_children())
        
        recent_failures = self.failed_commands[-50:] if self.failed_commands else []
        for cmd in recent_failures:
            timestamp = time.strftime("%H:%M:%S", time.localtime(cmd['timestamp']))
            resource = cmd['resource'].split('/')[-1] if '/' in cmd['resource'] else cmd['resource']
            
            self.failed_tree.insert('', 0, values=(
                timestamp,
                resource,
                cmd['command'][:50] + ('...' if len(cmd['command']) > 50 else ''),
                cmd['error'][:100] + ('...' if len(cmd['error']) > 100 else ''),
                cmd['attempts']
            ))
        
        # Schedule next refresh
        self.root.after(10000, self.refresh_diagnostics)  # Every 10 seconds
    
    def clear_command_history(self):
        """Clear command history"""
        if messagebox.askyesno("Clear History", "Clear all command history and statistics?"):
            self.command_history.clear()
            self.failed_commands.clear()
            self.add_log("🗑️ Command history cleared")
            self.refresh_diagnostics()
    
    def export_statistics(self):
        """Export command statistics to file"""
        try:
            from tkinter import filedialog
            
            filename = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
                title="Export Command Statistics"
            )
            
            if filename:
                stats = self.get_command_statistics()
                
                with open(filename, 'w') as f:
                    f.write("Rigol Multi-Instrument Control System - Command Statistics\n")
                    f.write("="*60 + "\n\n")
                    f.write(f"Export Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Total Commands: {stats['total']}\n")
                    f.write(f"Successful Commands: {stats['successful']}\n")
                    f.write(f"Failed Commands: {stats['failed']}\n")
                    f.write(f"Success Rate: {stats['success_rate']:.1f}%\n")
                    f.write(f"Average Attempts: {stats['avg_attempts']:.1f}\n\n")
                    
                    if self.failed_commands:
                        f.write("Failed Commands Detail:\n")
                        f.write("-" * 40 + "\n")
                        for cmd in self.failed_commands:
                            timestamp = time.strftime('%Y-%m-%d %H:%M:%S', 
                                                    time.localtime(cmd['timestamp']))
                            f.write(f"Time: {timestamp}\n")
                            f.write(f"Resource: {cmd['resource']}\n")
                            f.write(f"Command: {cmd['command']}\n")
                            f.write(f"Error: {cmd['error']}\n")
                            f.write(f"Attempts: {cmd['attempts']}\n\n")
                
                self.add_log(f"📊 Statistics exported to: {filename}")
                messagebox.showinfo("Export Complete", f"Statistics exported to:\n{filename}")
                
        except Exception as e:
            self.add_log(f"❌ Export failed: {e}")
            messagebox.showerror("Export Failed", f"Failed to export statistics:\n{e}")
    
    def create_status_bar(self, parent):
        """Create the bottom status bar"""
        status_frame = ttk.Frame(parent)
        status_frame.pack(
            fill=tk.X,
            side=tk.BOTTOM,
            padx=self.layout['outer_padx'],
            pady=(self.layout['inner_pad'], 0)
        )
        
        # Instrument status indicators
        self.status_labels = {}
        for name, info in self.instruments.items():
            status_frame_item = ttk.Frame(status_frame)
            status_frame_item.pack(side=tk.LEFT, padx=self.layout['inner_pad']//2)
            
            ttk.Label(status_frame_item, 
                     text=f"{info['model']}:",
                     style='TLabel').pack(side=tk.LEFT)
            
            status_label = ttk.Label(status_frame_item, 
                                   text="🔴 Disconnected",
                                   style='Disconnected.TLabel')
            status_label.pack(side=tk.LEFT, padx=5)
            
            self.status_labels[name] = status_label
        
        # Command statistics
        stats_frame = ttk.Frame(status_frame)
        stats_frame.pack(side=tk.LEFT, padx=self.layout['inner_pad'])
        
        ttk.Label(stats_frame, text="Commands:", style='TLabel').pack(side=tk.LEFT)
        self.command_stats_label = ttk.Label(stats_frame, text="0/0 (0%)", style='Connected.TLabel')
        self.command_stats_label.pack(side=tk.LEFT, padx=5)
        
        # Auto-refresh indicator
        self.refresh_status = ttk.Label(status_frame, text="Auto-refresh: OFF", style='TLabel')
        self.refresh_status.pack(side=tk.RIGHT, padx=self.layout['inner_pad']//2)
        
        # Update command stats periodically
        self.update_command_stats()
    
    def update_command_stats(self):
        """Update command statistics display"""
        stats = self.get_command_statistics()
        
        if stats['total'] > 0:
            stats_text = f"{stats['successful']}/{stats['total']} ({stats['success_rate']:.1f}%)"
            if stats['success_rate'] >= 95:
                self.command_stats_label.configure(text=stats_text, style='Connected.TLabel')
            elif stats['success_rate'] >= 80:
                self.command_stats_label.configure(text=stats_text, style='Warning.TLabel')
            else:
                self.command_stats_label.configure(text=stats_text, style='Disconnected.TLabel')
        else:
            self.command_stats_label.configure(text="0/0 (0%)", style='TLabel')
        
        # Schedule next update
        self.root.after(5000, self.update_command_stats)  # Update every 5 seconds
    
    def start_background_threads(self):
        """Start background threads for data acquisition"""
        # Thread for processing measurement updates
        self.measurement_thread = threading.Thread(target=self.measurement_worker, daemon=True)
        self.measurement_thread.start()
        
        # Thread for processing log updates
        self.log_thread = threading.Thread(target=self.log_worker, daemon=True)
        self.log_thread.start()
    
    def measurement_worker(self):
        """Background worker for measurement updates"""
        while True:
            try:
                # Get measurement data from queue
                data = self.measurement_queue.get(timeout=1)
                
                # Process the measurement data
                self.process_measurement_data(data)
                
                self.measurement_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Measurement worker error: {e}")
    
    def log_worker(self):
        """Background worker for log updates"""
        while True:
            try:
                # Get log message from queue
                message = self.log_queue.get(timeout=1)
                
                # Update log display in GUI thread
                self.root.after(0, self.update_log_display, message)
                
                self.log_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Log worker error: {e}")
    
    def add_log(self, message):
        """Add message to log queue"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}\n"
        self.log_queue.put(formatted_message)
    
    def update_log_display(self, message):
        """Update log display (called from GUI thread)"""
        self.log_text.insert(tk.END, message)
        self.log_text.see(tk.END)
        
        # Limit log size
        lines = int(self.log_text.index(tk.END).split('.')[0])
        if lines > 1000:
            self.log_text.delete('1.0', '500.0')
    
    def connect_to_pi(self):
        """Connect to Raspberry Pi"""
        def connect_thread():
            try:
                self.add_log("🔌 Connecting to Raspberry Pi (192.168.86.32)...")
                
                self.ssh_connection = connect_to_instrument(
                    ip_address='192.168.86.32',
                    port=22,
                    username='morgan',
                    password='Battlefield$$$321',
                    timeout=10
                )
                
                if self.ssh_connection:
                    self.connected = True
                    self.root.after(0, self.update_connection_status, True)
                    self.add_log("✅ Connected to Raspberry Pi successfully")
                    
                    # Auto-discover instruments
                    self.root.after(1000, self.discover_instruments)
                else:
                    self.add_log("❌ Failed to connect to Raspberry Pi")
                    self.root.after(0, self.update_connection_status, False)
                    
            except Exception as e:
                self.add_log(f"❌ Connection error: {e}")
                self.root.after(0, self.update_connection_status, False)
        
        threading.Thread(target=connect_thread, daemon=True).start()
    
    def update_connection_status(self, connected):
        """Update connection status display"""
        if connected:
            self.connection_status.configure(text="Connected", style='Connected.TLabel')
        else:
            self.connection_status.configure(text="Disconnected", style='Disconnected.TLabel')
    
    def discover_instruments(self):
        """Discover connected instruments"""
        if not self.connected:
            messagebox.showwarning("Warning", "Please connect to Pi first")
            return
        
        def discover_thread():
            try:
                self.add_log("🔍 Discovering instruments...")
                
                discover_cmd = """
cd ~/rigol
source venv/bin/activate
pip install pyusb --quiet

python << 'EOF'
import time

# Test each USBTMC device file directly
usbtmc_devices = [
    ('/dev/usbtmc0', 'USBTMC0'),
    ('/dev/usbtmc1', 'USBTMC1'), 
    ('/dev/usbtmc2', 'USBTMC2')
]

instruments = []

for device_path, device_name in usbtmc_devices:
    try:
        with open(device_path, 'w+b', buffering=0) as f:
            f.write(b'*IDN?\\n')
            time.sleep(0.1)
            response = f.read(1024)
            if response:
                idn = response.decode().strip()
                print(f'Found: {device_name} - {idn}')
                instruments.append((device_name, idn))
    except Exception as e:
        print(f'{device_name}: {e}')

print(f'Total instruments: {len(instruments)}')
EOF
"""
                
                result = send_command(self.ssh_connection, discover_cmd)
                
                if result:
                    self.parse_discovery_results(result)
                    
            except Exception as e:
                self.add_log(f"❌ Discovery error: {e}")
        
        threading.Thread(target=discover_thread, daemon=True).start()
    
    def parse_discovery_results(self, result):
        """Parse instrument discovery results"""
        lines = result.split('\n')
        
        for line in lines:
            if 'Found:' in line and ' - ' in line:
                parts = line.split(' - ', 1)
                if len(parts) >= 2:
                    device = parts[0].replace('Found: ', '').strip()
                    idn_response = parts[1].strip()
                    
                    # Map to resource path
                    if device == 'USBTMC0':
                        resource = '/dev/usbtmc0'
                    elif device == 'USBTMC1':
                        resource = '/dev/usbtmc1'
                    elif device == 'USBTMC2':
                        resource = '/dev/usbtmc2'
                    else:
                        resource = device
                    
                    # Identify instrument type
                    if 'DP832' in idn_response:
                        self.instruments['power_supply']['resource'] = resource
                        self.instruments['power_supply']['status'] = 'connected'
                        self.add_log(f"✅ Power Supply (DP832): {resource}")
                        self.root.after(0, self.update_instrument_status, 'power_supply', True)
                        
                    elif 'DL3021' in idn_response or 'DL3000' in idn_response:
                        self.instruments['electronic_load']['resource'] = resource
                        self.instruments['electronic_load']['status'] = 'connected'
                        self.add_log(f"✅ Electronic Load (DL3000): {resource}")
                        self.root.after(0, self.update_instrument_status, 'electronic_load', True)
                        
                    elif 'DS1102E' in idn_response:
                        self.instruments['oscilloscope']['resource'] = resource
                        self.instruments['oscilloscope']['status'] = 'connected'
                        self.add_log(f"✅ Oscilloscope (DS1102E): {resource}")
                        self.root.after(0, self.update_instrument_status, 'oscilloscope', True)
        
        self.add_log("🎉 Instrument discovery completed!")
    
    def update_instrument_status(self, instrument, connected):
        """Update instrument status in GUI"""
        if connected:
            self.status_labels[instrument].configure(text="🟢 Connected", 
                                                   style='Connected.TLabel')
        else:
            self.status_labels[instrument].configure(text="🔴 Disconnected", 
                                                   style='Disconnected.TLabel')
    
    def toggle_auto_refresh(self):
        """Toggle auto-refresh mode"""
        self.auto_refresh_enabled = not self.auto_refresh_enabled
        
        if self.auto_refresh_enabled:
            self.refresh_status.configure(text="Auto-refresh: ON", 
                                        style='Connected.TLabel')
            self.add_log("🔄 Auto-refresh enabled")
            self.start_auto_refresh()
        else:
            self.refresh_status.configure(text="Auto-refresh: OFF")
            self.add_log("⏸️ Auto-refresh disabled")
    
    def start_auto_refresh(self):
        """Start auto-refresh loop"""
        if self.auto_refresh_enabled and self.connected:
            # Update measurements
            self.update_all_measurements()
            
            # Schedule next update
            self.root.after(2000, self.start_auto_refresh)
    
    def update_all_measurements(self):
        """Update all instrument measurements"""
        def update_thread():
            try:
                # Update power supply
                if self.instruments['power_supply']['status'] == 'connected':
                    self.update_power_supply_measurements()
                
                # Update electronic load
                if self.instruments['electronic_load']['status'] == 'connected':
                    self.update_load_measurements()
                
                # Update oscilloscope
                if self.instruments['oscilloscope']['status'] == 'connected':
                    self.update_scope_measurements()
                    
            except Exception as e:
                self.add_log(f"❌ Measurement update error: {e}")
        
        threading.Thread(target=update_thread, daemon=True).start()
    
    def update_power_supply_measurements(self):
        """Update power supply measurements"""
        resource = self.instruments['power_supply']['resource']
        
        for ch in [1, 2, 3]:
            try:
                # Get measurements for each channel
                measurements = self.send_scpi_commands_batch(resource, [
                    f":INST:NSEL {ch}",
                    ":MEAS:VOLT?",
                    ":MEAS:CURR?",
                    ":VOLT?",
                    ":CURR?",
                    ":OUTP?"
                ])
                
                if measurements:
                    status = self.power_supply_status[ch]

                    # Parse measurements
                    try:
                        status['meas_voltage'] = float(measurements.get('MEAS:VOLT', 0.0) or 0.0)
                    except (TypeError, ValueError):
                        status['meas_voltage'] = 0.0

                    try:
                        status['meas_current'] = float(measurements.get('MEAS:CURR', 0.0) or 0.0)
                    except (TypeError, ValueError):
                        status['meas_current'] = 0.0

                    try:
                        status['set_voltage'] = float(measurements.get('VOLT', status['set_voltage']) or status['set_voltage'])
                    except (TypeError, ValueError):
                        pass

                    try:
                        status['set_current'] = float(measurements.get('CURR', status['set_current']) or status['set_current'])
                    except (TypeError, ValueError):
                        pass

                    output_raw = (measurements.get('OUTP') or '').strip().upper()
                    status['output'] = output_raw in {'1', 'ON', 'TRUE'}
                    status['power'] = status['meas_voltage'] * status['meas_current']

                    # Update GUI
                    self.root.after(0, self.update_ps_gui, ch)
                    
            except Exception as e:
                self.add_log(f"❌ PS CH{ch} measurement error: {e}")
    
    def send_verified_scpi_command(self, resource, command, expect_response=False, 
                                  instrument_type=None, verification_command=None):
        """
        Send SCPI command with verification and retry logic
        
        Args:
            resource: Device resource path
            command: SCPI command to send  
            expect_response: Whether to expect a response
            instrument_type: Type of instrument for validation
            verification_command: Optional command to verify the setting took effect
        
        Returns:
            dict: {'success': bool, 'response': str, 'attempts': int, 'error': str}
        """
        if not self.connected or not resource:
            return {'success': False, 'response': None, 'attempts': 0, 
                   'error': 'Not connected or no resource specified'}
        
        command_id = f"{resource}:{command}:{time.time()}"
        self.add_log(f"📤 Sending: {command} → {resource}")
        
        result = {
            'success': False,
            'response': None,
            'attempts': 0,
            'error': None
        }
        
        for attempt in range(1, self.max_retries + 1):
            result['attempts'] = attempt
            
            try:
                # Send the command
                response = self._send_single_scpi_command(resource, command, expect_response)
                
                if response is None and expect_response:
                    result['error'] = f"No response received (attempt {attempt})"
                    self.add_log(f"⚠️ Attempt {attempt}: No response")
                    time.sleep(0.5)  # Brief delay before retry
                    continue
                
                # Verify instrument identity if this is the first command to a device
                if attempt == 1 and instrument_type:
                    identity_check = self._verify_instrument_identity(resource, instrument_type)
                    if not identity_check['success']:
                        result['error'] = f"Instrument identity verification failed: {identity_check['error']}"
                        self.add_log(f"❌ Identity check failed: {identity_check['error']}")
                        break
                
                # Optional verification command to confirm the setting
                if verification_command and not expect_response:
                    time.sleep(0.1)  # Allow command to take effect
                    verify_response = self._send_single_scpi_command(resource, verification_command, True)
                    if verify_response:
                        self.add_log(f"✅ Verified: {verification_command} → {verify_response.strip()}")
                
                # Success!
                result['success'] = True
                result['response'] = response
                
                # Log success
                if expect_response:
                    self.add_log(f"📥 Response: {response.strip() if response else 'None'}")
                else:
                    self.add_log(f"✅ Command sent successfully")
                
                # Record successful command
                self.command_history.append({
                    'timestamp': time.time(),
                    'command': command,
                    'resource': resource,
                    'success': True,
                    'attempts': attempt,
                    'response': response
                })
                
                break
                
            except Exception as e:
                result['error'] = f"Attempt {attempt} failed: {str(e)}"
                self.add_log(f"❌ Attempt {attempt} error: {e}")
                
                if attempt < self.max_retries:
                    time.sleep(1.0)  # Longer delay for exceptions
                
        # Record failed command if all attempts failed
        if not result['success']:
            self.failed_commands.append({
                'timestamp': time.time(),
                'command': command,
                'resource': resource,
                'error': result['error'],
                'attempts': result['attempts']
            })
            self.add_log(f"💥 Command failed after {result['attempts']} attempts: {result['error']}")
        
        return result
    
    def _send_single_scpi_command(self, resource, command, expect_response=False):
        """Send a single SCPI command with timeout"""
        if resource.startswith('/dev/usbtmc'):
            # Direct device file access
            scpi_cmd = f"""
cd ~/rigol
source venv/bin/activate
timeout {self.command_timeout} python << 'EOF'
import time
import warnings
import signal

def timeout_handler(signum, frame):
    raise TimeoutError("Command timed out")

signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm({int(self.command_timeout)})

warnings.filterwarnings('ignore')

try:
    device_path = '{resource}'
    
    with open(device_path, 'w+b', buffering=0) as f:
        # Send command
        f.write(b'{command}\\n')
        time.sleep(0.1)
        
        {"# Read response" if expect_response else "# Command sent, no response expected"}
        {f"response = f.read(1024).decode().strip(); print(f'RESPONSE:{{response}}')" if expect_response else "print('SUCCESS:Command executed')"}
        
except TimeoutError:
    print('ERROR:Command timed out')
except Exception as e:
    print(f'ERROR:{{e}}')
finally:
    signal.alarm(0)
EOF
"""
        else:
            # PyVISA resource string (fallback)
            scpi_cmd = f"""
cd ~/rigol
source venv/bin/activate
timeout {self.command_timeout} python << 'EOF'
import pyvisa
import time
import warnings
import signal

def timeout_handler(signum, frame):
    raise TimeoutError("Command timed out")

signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm({int(self.command_timeout)})

warnings.filterwarnings('ignore', message='.*TCPIP:instr resource discovery is limited.*')
warnings.filterwarnings('ignore', message='.*TCPIP::hislip resource discovery requires.*')

inst = None
try:
    rm = pyvisa.ResourceManager('@py')
    inst = rm.open_resource('{resource}')
    inst.timeout = {int(self.command_timeout * 1000)}
    
    {"response = inst.query('" + command + "')" if expect_response else "inst.write('" + command + "')"}
    {"print(f'RESPONSE:{response.strip()}')" if expect_response else "print('SUCCESS:Command executed')"}
    
except TimeoutError:
    print('ERROR:Command timed out')
except Exception as e:
    print(f'ERROR:{{e}}')
finally:
    signal.alarm(0)
    if inst:
        try:
            inst.close()
        except:
            pass
    try:
        rm.close()
    except:
        pass
EOF
"""
        
        result = send_command(self.ssh_connection, scpi_cmd)
        
        if result:
            lines = result.strip().split('\n')
            for line in lines:
                if line.startswith('SUCCESS:'):
                    return "SUCCESS" if not expect_response else None
                elif line.startswith('RESPONSE:'):
                    return line[9:]  # Remove 'RESPONSE:' prefix
                elif line.startswith('ERROR:'):
                    raise Exception(line[6:])  # Remove 'ERROR:' prefix
        
        return None
    
    def _verify_instrument_identity(self, resource, expected_type):
        """Verify we're talking to the correct instrument"""
        try:
            identity_response = self._send_single_scpi_command(resource, "*IDN?", True)
            
            if not identity_response:
                return {'success': False, 'error': 'No identity response'}
            
            identity = identity_response.strip().upper()
            
            # Verify instrument type matches expected
            type_checks = {
                'power_supply': ['DP832', 'DP8'],
                'electronic_load': ['DL3021', 'DL3000', 'DL30'],
                'oscilloscope': ['DS1102E', 'DS110']
            }
            
            if expected_type in type_checks:
                expected_patterns = type_checks[expected_type]
                if not any(pattern in identity for pattern in expected_patterns):
                    return {'success': False, 
                           'error': f'Wrong instrument type. Expected {expected_type}, got: {identity}'}
            
            return {'success': True, 'identity': identity}
            
        except Exception as e:
            return {'success': False, 'error': f'Identity check failed: {e}'}
    
    def get_command_statistics(self):
        """Get statistics about command success/failure rates"""
        total_commands = len(self.command_history) + len(self.failed_commands)
        if total_commands == 0:
            return {
                'total': 0, 
                'successful': 0, 
                'failed': 0,
                'success_rate': 0, 
                'avg_attempts': 0
            }
        
        successful_commands = len(self.command_history)
        success_rate = (successful_commands / total_commands) * 100
        
        total_attempts = sum(cmd.get('attempts', 1) for cmd in self.command_history)
        total_attempts += sum(cmd.get('attempts', 1) for cmd in self.failed_commands)
        avg_attempts = total_attempts / total_commands
        
        return {
            'total': total_commands,
            'successful': successful_commands,
            'failed': len(self.failed_commands),
            'success_rate': success_rate,
            'avg_attempts': avg_attempts
        }
    
    def send_scpi_commands_batch(self, resource, commands):
        """Send batch of SCPI commands (simplified implementation)"""
        results = {}

        if not resource:
            return results

        for command in commands:
            command = command.strip()
            if not command:
                continue

            expect_response = command.endswith('?')

            try:
                response = self._send_single_scpi_command(resource, command, expect_response)

                if expect_response:
                    key = command.lstrip(':').rstrip('?')
                    key = key.upper()
                    results[key] = (response or '').strip()

            except Exception as e:
                error_key = f"ERROR:{command}"
                results[error_key] = str(e)
                self.add_log(f"❌ Batch command failed ({command}): {e}")

        return results
    
    def update_ps_gui(self, channel):
        """Update power supply GUI elements"""
        status = self.power_supply_status[channel]
        meas_v = status['meas_voltage']
        meas_i = status['meas_current']
        set_v = status['set_voltage']
        set_i = status['set_current']
        power = status['power']
        
        # Update overview
        self.ps_overview_labels[channel]['status'].configure(
            text="🟢 ON" if status['output'] else "🔴 OFF")
        self.ps_overview_labels[channel]['voltage'].configure(
            text=f"Meas {meas_v:.3f}V (Set {set_v:.3f}V)")
        self.ps_overview_labels[channel]['current'].configure(
            text=f"Meas {meas_i:.3f}A (Set {set_i:.3f}A)")
        self.ps_overview_labels[channel]['power'].configure(
            text=f"{power:.2f}W")
        
        # Update status table
        self.ps_tree.item(f'ch{channel}', values=(
            f'CH{channel}',
            'ON' if status['output'] else 'OFF',
            f"{set_v:.3f}V",
            f"{meas_v:.3f}V",
            f"{set_i:.3f}A",
            f"{meas_i:.3f}A",
            f"{power:.2f}W"
        ))
    
    def update_load_measurements(self):
        """Update electronic load measurements"""
        # Implementation would go here
        pass
    
    def update_scope_measurements(self):
        """Update oscilloscope measurements"""
        # Implementation would go here
        pass
    
    def update_plots(self, frame):
        """Update real-time plots"""
        # Clear axes
        self.ax1.clear()
        self.ax2.clear()
        self.ax3.clear()
        self.ax4.clear()
        
        # Get current time
        current_time = time.time()
        
        # Update measurement history
        if len(self.measurement_history['power_supply']['time']) > 100:
            # Keep only last 100 points
            for key in self.measurement_history['power_supply']:
                self.measurement_history['power_supply'][key] = \
                    self.measurement_history['power_supply'][key][-100:]
        
        # Add current measurements
        self.measurement_history['power_supply']['time'].append(current_time)
        
        for ch in [1, 2, 3]:
            status = self.power_supply_status[ch]
            self.measurement_history['power_supply'][f'ch{ch}_voltage'].append(status['meas_voltage'])
            self.measurement_history['power_supply'][f'ch{ch}_current'].append(status['meas_current'])
            self.measurement_history['power_supply'][f'ch{ch}_power'].append(status['power'])
        
        # Plot data if available
        times = self.measurement_history['power_supply']['time']
        if len(times) > 1:
            # Convert to relative time
            times = [(t - times[0]) for t in times]
            
            # Plot voltages
            self.ax1.plot(times, self.measurement_history['power_supply']['ch1_voltage'], 
                         'r-', label='CH1', linewidth=2)
            self.ax1.plot(times, self.measurement_history['power_supply']['ch2_voltage'], 
                         'g-', label='CH2', linewidth=2)
            self.ax1.plot(times, self.measurement_history['power_supply']['ch3_voltage'], 
                         'b-', label='CH3', linewidth=2)
            
            # Plot currents
            self.ax2.plot(times, self.measurement_history['power_supply']['ch1_current'], 
                         'r-', label='CH1', linewidth=2)
            self.ax2.plot(times, self.measurement_history['power_supply']['ch2_current'], 
                         'g-', label='CH2', linewidth=2)
            self.ax2.plot(times, self.measurement_history['power_supply']['ch3_current'], 
                         'b-', label='CH3', linewidth=2)
            
            # Plot powers
            total_power = [p1 + p2 + p3 for p1, p2, p3 in zip(
                self.measurement_history['power_supply']['ch1_power'],
                self.measurement_history['power_supply']['ch2_power'],
                self.measurement_history['power_supply']['ch3_power'])]
            
            self.ax4.plot(times, total_power, 'orange', linewidth=2)
        
        # Configure axes
        self.ax1.set_title('Power Supply - Voltage', color='white')
        self.ax1.set_ylabel('Voltage (V)', color='white')
        self.ax1.legend()
        self.ax1.grid(True, alpha=0.3)
        
        self.ax2.set_title('Power Supply - Current', color='white')
        self.ax2.set_ylabel('Current (A)', color='white')
        self.ax2.legend()
        self.ax2.grid(True, alpha=0.3)
        
        self.ax3.set_title('Electronic Load', color='white')
        self.ax3.set_ylabel('Power (W)', color='white')
        self.ax3.grid(True, alpha=0.3)
        
        self.ax4.set_title('Total Power', color='white')
        self.ax4.set_ylabel('Power (W)', color='white')
        self.ax4.set_xlabel('Time (s)', color='white')
        self.ax4.grid(True, alpha=0.3)
        
        # Style adjustments
        for ax in [self.ax1, self.ax2, self.ax3, self.ax4]:
            ax.set_facecolor('#404040')
            ax.tick_params(colors='white')
    
    # Control methods with verification
    def toggle_ps_output(self, channel):
        """Toggle power supply output with verification"""
        resource = self.instruments['power_supply']['resource']
        if not resource:
            self.add_log("❌ Power supply not connected")
            return
            
        try:
            # First select the channel
            select_result = self.send_verified_scpi_command(
                resource, f":INST:NSEL {channel}", 
                instrument_type='power_supply'
            )
            
            if not select_result['success']:
                self.add_log(f"❌ Failed to select PS CH{channel}: {select_result['error']}")
                self.ps_controls[channel]['output_var'].set(self.power_supply_status[channel]['output'])
                return
            
            # Get current output state
            current_state = self.power_supply_status[channel]['output']
            new_state = "OFF" if current_state else "ON"
            
            # Send output command
            output_result = self.send_verified_scpi_command(
                resource, f":OUTP {new_state}",
                verification_command=":OUTP?"
            )
            
            if output_result['success']:
                self.power_supply_status[channel]['output'] = not current_state
                self.ps_controls[channel]['output_var'].set(self.power_supply_status[channel]['output'])

                if new_state == "ON":
                    set_v = self.power_supply_status[channel]['set_voltage']
                    set_i = self.power_supply_status[channel]['set_current']
                    self.add_log(
                        f"✅ PS CH{channel} output: {new_state} - Supplying up to {set_v:.3f}V @ {set_i:.3f}A"
                    )
                    self.add_log(f"⚡ PS CH{channel}: Output ENABLED - voltage now available at terminals")
                else:
                    self.add_log(f"✅ PS CH{channel} output: {new_state} - No power at terminals")
                self.update_ps_gui(channel)
            else:
                self.add_log(f"❌ Failed to toggle PS CH{channel}: {output_result['error']}")
                self.ps_controls[channel]['output_var'].set(current_state)
                
        except Exception as e:
            self.add_log(f"❌ PS CH{channel} toggle error: {e}")
            self.ps_controls[channel]['output_var'].set(self.power_supply_status[channel]['output'])
    
    def set_ps_values(self, channel):
        """Set power supply values with verification"""
        resource = self.instruments['power_supply']['resource']
        if not resource:
            self.add_log("❌ Power supply not connected")
            return
            
        try:
            voltage = float(self.ps_controls[channel]['voltage_var'].get())
            current = float(self.ps_controls[channel]['current_var'].get())
            
            # Validate limits
            max_v = self.power_supply_status[channel]['voltage_limit']
            max_i = self.power_supply_status[channel]['current_limit']
            
            if not (0 <= voltage <= max_v):
                self.add_log(f"❌ CH{channel} voltage must be 0-{max_v}V")
                return
            if not (0 <= current <= max_i):
                self.add_log(f"❌ CH{channel} current must be 0-{max_i}A")
                return
            
            # Select channel
            select_result = self.send_verified_scpi_command(
                resource, f":INST:NSEL {channel}",
                instrument_type='power_supply'
            )
            
            if not select_result['success']:
                self.add_log(f"❌ Failed to select PS CH{channel}")
                return
            
            # Set voltage
            voltage_result = self.send_verified_scpi_command(
                resource, f":VOLT {voltage}",
                verification_command=":VOLT?"
            )
            
            # Set current
            current_result = self.send_verified_scpi_command(
                resource, f":CURR {current}",
                verification_command=":CURR?"
            )
            
            if voltage_result['success'] and current_result['success']:
                self.add_log(f"✅ PS CH{channel} set: {voltage:.3f}V, {current:.3f}A")
                self.add_log(f"💡 PS CH{channel}: Settings saved. Turn OUTPUT ON to supply power.")

                # Update local status
                status = self.power_supply_status[channel]
                status['set_voltage'] = voltage
                status['set_current'] = current

                # Keep UI controls aligned with validated values
                self.ps_controls[channel]['voltage_var'].set(voltage)
                self.ps_controls[channel]['current_var'].set(current)

                self.update_ps_gui(channel)
            else:
                errors = []
                if not voltage_result['success']:
                    errors.append(f"voltage: {voltage_result['error']}")
                if not current_result['success']:
                    errors.append(f"current: {current_result['error']}")
                self.add_log(f"❌ PS CH{channel} set failed: {'; '.join(errors)}")
                
        except Exception as e:
            self.add_log(f"❌ PS CH{channel} set error: {e}")
    
    def toggle_load_input(self):
        """Toggle electronic load input with verification"""
        resource = self.instruments['electronic_load']['resource']
        if not resource:
            self.add_log("❌ Electronic load not connected")
            return
            
        try:
            current_state = self.load_status['input']
            new_state = "OFF" if current_state else "ON"
            
            result = self.send_verified_scpi_command(
                resource, f":INP {new_state}",
                instrument_type='electronic_load',
                verification_command=":INP?"
            )
            
            if result['success']:
                self.load_status['input'] = not current_state
                self.add_log(f"✅ Load input: {new_state}")
            else:
                self.add_log(f"❌ Failed to toggle load input: {result['error']}")
                
        except Exception as e:
            self.add_log(f"❌ Load input toggle error: {e}")
    
    def on_load_mode_change(self, event=None):
        """Handle load mode change with verification"""
        resource = self.instruments['electronic_load']['resource']
        if not resource:
            self.add_log("❌ Electronic load not connected")
            return
            
        try:
            mode = self.load_mode_var.get()
            mode_map = {'CC': 'CURR', 'CV': 'VOLT', 'CP': 'POW', 'CR': 'RES'}
            scpi_mode = mode_map.get(mode, 'CURR')
            
            result = self.send_verified_scpi_command(
                resource, f":FUNC {scpi_mode}",
                instrument_type='electronic_load',
                verification_command=":FUNC?"
            )
            
            if result['success']:
                self.load_status['mode'] = mode
                self.add_log(f"✅ Load mode: {mode}")
            else:
                self.add_log(f"❌ Failed to set load mode: {result['error']}")
                
        except Exception as e:
            self.add_log(f"❌ Load mode change error: {e}")
    
    def set_load_parameter(self, param_name):
        """Set load parameter with verification"""
        resource = self.instruments['electronic_load']['resource']
        if not resource:
            self.add_log("❌ Electronic load not connected")
            return
            
        try:
            value = self.load_controls[param_name]['var'].get()
            
            # Map parameter names to SCPI commands
            param_map = {
                'current': 'CURR',
                'voltage': 'VOLT', 
                'power': 'POW',
                'resistance': 'RES'
            }
            
            scpi_param = param_map.get(param_name)
            if not scpi_param:
                self.add_log(f"❌ Unknown parameter: {param_name}")
                return
            
            result = self.send_verified_scpi_command(
                resource, f":{scpi_param} {value}",
                instrument_type='electronic_load',
                verification_command=f":{scpi_param}?"
            )
            
            if result['success']:
                self.load_status[param_name] = value
                self.add_log(f"✅ Load {param_name}: {value}")
            else:
                self.add_log(f"❌ Failed to set load {param_name}: {result['error']}")
                
        except Exception as e:
            self.add_log(f"❌ Load {param_name} set error: {e}")
    
    def set_timebase(self):
        """Set oscilloscope timebase with verification"""
        resource = self.instruments['oscilloscope']['resource']
        if not resource:
            self.add_log("❌ Oscilloscope not connected")
            return
            
        try:
            timebase = float(self.timebase_var.get())
            
            result = self.send_verified_scpi_command(
                resource, f":TIM:SCAL {timebase}",
                instrument_type='oscilloscope',
                verification_command=":TIM:SCAL?"
            )
            
            if result['success']:
                self.scope_status['timebase'] = timebase
                self.add_log(f"✅ Scope timebase: {timebase} s/div")
            else:
                self.add_log(f"❌ Failed to set timebase: {result['error']}")
                
        except Exception as e:
            self.add_log(f"❌ Timebase set error: {e}")
    
    def scope_auto_setup(self):
        """Perform scope auto setup with verification"""
        resource = self.instruments['oscilloscope']['resource']
        if not resource:
            self.add_log("❌ Oscilloscope not connected")
            return
            
        try:
            result = self.send_verified_scpi_command(
                resource, ":AUT",
                instrument_type='oscilloscope'
            )
            
            if result['success']:
                self.add_log("✅ Scope auto setup completed")
                # Update scope status after auto setup
                time.sleep(1)  # Allow auto setup to complete
                self.update_scope_measurements()
            else:
                self.add_log(f"❌ Scope auto setup failed: {result['error']}")
                
        except Exception as e:
            self.add_log(f"❌ Scope auto setup error: {e}")
    
    def toggle_scope_channel(self, channel):
        """Toggle scope channel with verification"""
        resource = self.instruments['oscilloscope']['resource']
        if not resource:
            self.add_log("❌ Oscilloscope not connected")
            return
            
        try:
            enabled = self.scope_controls[channel]['enabled_var'].get()
            state = "ON" if enabled else "OFF"
            
            result = self.send_verified_scpi_command(
                resource, f":CHAN{channel}:DISP {state}",
                instrument_type='oscilloscope',
                verification_command=f":CHAN{channel}:DISP?"
            )
            
            if result['success']:
                self.scope_status[f'channel_{channel}']['enabled'] = enabled
                self.add_log(f"✅ Scope CH{channel}: {state}")
            else:
                self.add_log(f"❌ Failed to toggle scope CH{channel}: {result['error']}")
                
        except Exception as e:
            self.add_log(f"❌ Scope CH{channel} toggle error: {e}")
    
    def emergency_shutdown(self):
        """Emergency shutdown all instruments with verification"""
        if messagebox.askyesno("Emergency Shutdown", 
                              "⚠️ This will immediately shut down all instruments!\n\nContinue?"):
            self.add_log("🚨 EMERGENCY SHUTDOWN INITIATED!")
            shutdown_success = True
            
            # Power Supply - Turn off all outputs
            if self.instruments['power_supply']['status'] == 'connected':
                ps_resource = self.instruments['power_supply']['resource']
                self.add_log("🔴 Emergency shutdown: Power Supply...")
                
                for channel in [1, 2, 3]:
                    try:
                        # Select channel
                        self.send_verified_scpi_command(
                            ps_resource, f":INST:NSEL {channel}"
                        )
                        
                        # Turn off output
                        result = self.send_verified_scpi_command(
                            ps_resource, ":OUTP OFF",
                            verification_command=":OUTP?"
                        )
                        
                        if result['success']:
                            self.add_log(f"   ✅ CH{channel}: OUTPUT OFF")
                            self.power_supply_status[channel]['output'] = False
                        else:
                            self.add_log(f"   ❌ CH{channel}: Failed to turn off")
                            shutdown_success = False
                            
                        # Set safe values
                        self.send_verified_scpi_command(ps_resource, ":VOLT 0")
                        self.send_verified_scpi_command(ps_resource, ":CURR 0.1")
                        
                    except Exception as e:
                        self.add_log(f"   ❌ CH{channel}: Emergency shutdown error: {e}")
                        shutdown_success = False
            
            # Electronic Load - Turn off input
            if self.instruments['electronic_load']['status'] == 'connected':
                load_resource = self.instruments['electronic_load']['resource']
                self.add_log("🔴 Emergency shutdown: Electronic Load...")
                
                try:
                    result = self.send_verified_scpi_command(
                        load_resource, ":INP OFF",
                        verification_command=":INP?"
                    )
                    
                    if result['success']:
                        self.add_log("   ✅ INPUT: OFF")
                        self.load_status['input'] = False
                    else:
                        self.add_log("   ❌ Failed to turn off input")
                        shutdown_success = False
                        
                except Exception as e:
                    self.add_log(f"   ❌ Load emergency shutdown error: {e}")
                    shutdown_success = False
            
            # Oscilloscope - Stop acquisition
            if self.instruments['oscilloscope']['status'] == 'connected':
                scope_resource = self.instruments['oscilloscope']['resource']
                self.add_log("🔴 Emergency shutdown: Oscilloscope...")
                
                try:
                    result = self.send_verified_scpi_command(
                        scope_resource, ":STOP"
                    )
                    
                    if result['success']:
                        self.add_log("   ✅ ACQUISITION: STOPPED")
                    else:
                        self.add_log("   ❌ Failed to stop acquisition")
                        
                except Exception as e:
                    self.add_log(f"   ❌ Scope emergency shutdown error: {e}")
            
            if shutdown_success:
                self.add_log("✅ Emergency shutdown completed safely")
                messagebox.showinfo("Emergency Shutdown", 
                                   "✅ Emergency shutdown completed safely")
            else:
                self.add_log("⚠️ Emergency shutdown completed with some errors")
                messagebox.showwarning("Emergency Shutdown", 
                                      "⚠️ Emergency shutdown completed but some commands failed.\nCheck the log for details.")
            
            # Update GUI status
            for ch in [1, 2, 3]:
                self.update_ps_gui(ch)
                
        else:
            self.add_log("❌ Emergency shutdown cancelled")
    
    def process_measurement_data(self, data):
        """Process incoming measurement data"""
        # This would handle real measurement data from instruments
        pass
    
    def on_closing(self):
        """Handle window close event"""
        if self.connected:
            if messagebox.askyesno("Quit", "Disconnect from Pi and exit?"):
                self.add_log("👋 Disconnecting from Pi...")
                if self.ssh_connection:
                    disconnect_from_instrument(self.ssh_connection)
                self.root.destroy()
        else:
            self.root.destroy()

def main():
    """Main function to start the GUI"""
    # Check if backend is available
    try:
        from Connect_to_Rigol_Instruments import connect_to_instrument
        print("✅ Backend modules imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import backend modules: {e}")
        print("Make sure Connect_to_Rigol_Instruments.py is in the same directory")
        return
    
    # Create and run GUI
    root = tk.Tk()
    app = RigolGUI(root)
    
    print("🚀 Starting Rigol Multi-Instrument GUI...")
    root.mainloop()

if __name__ == "__main__":
    main()
