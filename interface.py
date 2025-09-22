import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Any, Optional


class TkHeadMouseUI:
    """
    UI de ajustes para o Head Mouse (refatorada para clareza e aparência).

    Principais melhorias de UX/UI:
    - Layout organizado em abas (Notebook) para reduzir carga visual.
    - Linhas consistentes com rótulo à esquerda, controle ao centro e valor/entrada à direita.
    - Escalas com Spinbox numérico acoplado e label de valor ao vivo.
    - Barra de ações fixa no rodapé (Aplicar, Sincronizar, Fechar) + dicas.
    - Indicadores de status para Controle e EdgeAccel (com alternância).
    - Tooltips (passar o mouse) explicando cada parâmetro.
    - Estilos ttk padronizados, espaçamentos e tamanhos mínimos coerentes.
    - Atalhos de teclado mantidos (F1/F2/F4) + hints no botão.

    API pública preservada (métodos/padrões), para drop-in replacement.
    """

    def __init__(
        self,
        presets: List[Dict[str, Any]],
        current_preset_provider: Callable[[], int],
        apply_preset: Callable[[int], None],
        get_state: Callable[[], Dict[str, Any]],
        set_state: Callable[[Dict[str, Any]], None],
        toggle_control: Optional[Callable[[], None]] = None,
        toggle_edgeaccel: Optional[Callable[[], None]] = None,
        request_recalibrate: Optional[Callable[[], None]] = None,
        title: str = "Ajustes - Head Mouse",
    ):
        self._presets = presets
        self._get_current_preset = current_preset_provider
        self._apply_preset = apply_preset
        self._get_state = get_state
        self._set_state = set_state
        self._toggle_control = toggle_control
        self._toggle_edge = toggle_edgeaccel
        self._request_recalibrate = request_recalibrate

        # --- Tk root ---
        self.root = tk.Tk()
        self.root.title(title)
        self.root.minsize(560, 560)
        try:
            self.root.wm_attributes("-topmost", True)
        except Exception:
            pass

        self._build_styles()
        self._build_vars()
        self._build_layout()
        self._bind_shortcuts()

        self._last_preset_idx = None
        self.alive = True
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- infra ----------
    def _on_close(self):
        self.alive = False
        try:
            self.root.destroy()
        except Exception:
            pass

    def pump(self):
        """Chame a cada frame para manter a janela viva (sem mainloop)."""
        if not self.alive:
            return
        try:
            self.root.update_idletasks()
            self.root.update()
        except tk.TclError:
            self.alive = False

    # ---------- estilos ----------
    def _build_styles(self):
        s = ttk.Style()
        # Tenta usar um tema moderno e consistente
        try:
            s.theme_use("clam")
        except Exception:
            pass

        # Tamanhos/paddings
        s.configure("TLabel", padding=(2, 6))
        s.configure("TButton", padding=(8, 6))
        s.configure("TCheckbutton", padding=(2, 6))
        s.configure("TLabelframe", padding=10)
        s.configure("Header.TLabel", font=("Segoe UI", 12, "bold"))
        s.configure("Subtle.TLabel", foreground="#555")
        s.configure("Status.On.TLabel", foreground="#0a7b24", font=("Segoe UI", 10, "bold"))
        s.configure("Status.Off.TLabel", foreground="#a33", font=("Segoe UI", 10, "bold"))
        s.configure("Value.TLabel", foreground="#222")

    # ---------- tooltips ----------
    class _ToolTip:
        def __init__(self, widget, text: str):
            self.widget = widget
            self.text = text
            self.tipwin = None
            widget.bind("<Enter>", self._show)
            widget.bind("<Leave>", self._hide)

        def _show(self, _):
            if self.tipwin or not self.text:
                return
            x, y, cx, cy = self.widget.bbox("insert") if self.widget.winfo_ismapped() else (0, 0, 0, 0)
            x += self.widget.winfo_rootx() + 20
            y += self.widget.winfo_rooty() + 20
            self.tipwin = tw = tk.Toplevel(self.widget)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f"+{x}+{y}")
            lbl = ttk.Label(tw, text=self.text, relief=tk.SOLID, borderwidth=1, padding=6)
            lbl.pack()

        def _hide(self, _):
            if self.tipwin:
                self.tipwin.destroy()
                self.tipwin = None

    # ---------- vars ----------
    def _build_vars(self):
        st = self._get_state()

        self.var_preset = tk.StringVar(value=str(self._get_current_preset()))

        self.var_deadzone = tk.DoubleVar(value=float(st["deadzone_deg"]))
        self.var_gain_yaw = tk.DoubleVar(value=float(st["gain_yaw"]))
        self.var_gain_pitch = tk.DoubleVar(value=float(st["gain_pitch"]))
        self.var_gain_power = tk.DoubleVar(value=float(st["gain_power"]))
        self.var_max_speed = tk.IntVar(value=int(st["max_speed_px"]))

        self.var_ema_alpha = tk.DoubleVar(value=float(st["ema_alpha"]))
        self.var_vel_ema_alpha = tk.DoubleVar(value=float(st["vel_ema_alpha"]))

        self.var_edge_margin = tk.IntVar(value=int(st["edge_margin"]))
        self.var_edge_max = tk.DoubleVar(value=float(st["edge_accel_max"]))
        self.var_edge_rate = tk.DoubleVar(value=float(st["edge_accel_rate"]))
        self.var_edge_decay = tk.DoubleVar(value=float(st["edge_decay_rate"]))

        self.var_yaw_strong_deg = tk.DoubleVar(value=float(st["yaw_strong_deg"]))
        self.var_yaw_strong_rate = tk.DoubleVar(value=float(st["yaw_strong_rate"]))

        self.var_invert_y = tk.BooleanVar(value=bool(st["INVERT_Y"]))
        self.var_edge_enabled = tk.BooleanVar(value=bool(st["EDGE_ACCEL_ENABLED"]))

        # Status text no rodapé
        self.var_status = tk.StringVar(value="Pronto.")

    # ---------- layout ----------
    def _build_layout(self):
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        # Cabeçalho
        header = ttk.Frame(root, padding=(12, 10))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        ttk.Label(header, text="Head Mouse — Ajustes", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="Ajuste os parâmetros nas abas abaixo. Use ‘Aplicar’ para enviar ao sistema.", style="Subtle.TLabel").grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

        # Indicadores de status à direita
        self.lbl_status_control = ttk.Label(header, text=self._status_text(self._toggle_control is not None, True), style="Status.On.TLabel")
        self.lbl_status_control.grid(row=0, column=2, sticky="e", padx=(8, 0))
        self.lbl_status_edge = ttk.Label(header, text=self._status_text(self.var_edge_enabled.get(), False), style=("Status.On.TLabel" if self.var_edge_enabled.get() else "Status.Off.TLabel"))
        self.lbl_status_edge.grid(row=0, column=3, sticky="e")

        # Corpo com abas
        nb = ttk.Notebook(root)
        nb.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        # --- Aba: Presets ---
        tab_preset = ttk.Frame(nb)
        nb.add(tab_preset, text="Presets")
        tab_preset.columnconfigure(0, weight=1)

        box = ttk.Labelframe(tab_preset, text="Preset atual")
        box.grid(row=0, column=0, sticky="ew", padx=6, pady=6)
        names = [p.get("name", f"Preset {i}") for i, p in enumerate(self._presets)]
        self.combo = ttk.Combobox(box, state="readonly", values=names, textvariable=self.var_preset)
        self.combo.bind("<<ComboboxSelected>>", self._on_preset_change)
        ttk.Label(box, text="Selecione um preset; mudar controles nas abas cria um override temporário.").grid(row=0, column=0, sticky="w", padx=6, pady=(6, 0))
        self.combo.grid(row=1, column=0, sticky="ew", padx=6, pady=(4, 8))
        box.columnconfigure(0, weight=1)

        # --- Aba: Sensibilidade ---
        tab_sens = ttk.Frame(nb)
        nb.add(tab_sens, text="Sensibilidade")
        self._grid_of_scales(tab_sens, [
            ("Deadzone", self.var_deadzone, 0.0, 15.0, 0.1, False, "graus sem resposta ao centro"),
            ("Gain Yaw", self.var_gain_yaw, 0.0, 30.0, 0.1, False, "multiplicador de sensibilidade em yaw"),
            ("Gain Pitch", self.var_gain_pitch, 0.0, 30.0, 0.1, False, "multiplicador de sensibilidade em pitch"),
            ("Power", self.var_gain_power, 0.5, 2.5, 0.01, False, "curva potência (1 = linear)"),
            ("Max Speed", self.var_max_speed, 1, 100, 1, True, "velocidade máxima do cursor (px)"),
        ])

        # --- Aba: Suavização ---
        tab_smooth = ttk.Frame(nb)
        nb.add(tab_smooth, text="Suavização")
        self._grid_of_scales(tab_smooth, [
            ("Angle EMA", self.var_ema_alpha, 0.0, 1.0, 0.01, False, "alpha do filtro exponencial nos ângulos"),
            ("Vel EMA", self.var_vel_ema_alpha, 0.0, 1.0, 0.01, False, "alpha do filtro exponencial na velocidade"),
        ])

        # --- Aba: EdgeAccel / Stick ---
        tab_edge = ttk.Frame(nb)
        nb.add(tab_edge, text="EdgeAccel / Stick")
        self._grid_of_scales(tab_edge, [
            ("Edge Margin", self.var_edge_margin, 0, 200, 1, True, "margem da tela (px) para detecção de borda"),
            ("Edge Max (x)", self.var_edge_max, 0.0, 10.0, 0.1, False, "fator máx. de aceleração na borda"),
            ("Edge Rate (/s)", self.var_edge_rate, 0.0, 10.0, 0.1, False, "taxa de acumulação de aceleração"),
            ("Edge Decay (/s)", self.var_edge_decay, 0.0, 10.0, 0.1, False, "taxa de decaimento quando fora da borda"),
            ("Yaw Forte (deg)", self.var_yaw_strong_deg, 0.0, 30.0, 0.1, False, "limiar de yaw para boost"),
            ("Yaw Forte Rate", self.var_yaw_strong_rate, 0.0, 10.0, 0.1, False, "taxa de acumulação do boost"),
        ])

        # --- Aba: Opções ---
        tab_opts = ttk.Frame(nb)
        nb.add(tab_opts, text="Opções")
        tab_opts.columnconfigure(0, weight=1)
        box_opts = ttk.Labelframe(tab_opts, text="Comportamento")
        box_opts.grid(row=0, column=0, sticky="ew", padx=6, pady=6)
        ttk.Checkbutton(box_opts, text="Invert Y", variable=self.var_invert_y).grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.chk_edge_enabled = ttk.Checkbutton(box_opts, text="EdgeAccelX habilitado", variable=self.var_edge_enabled, command=self._reflect_edge_toggle)
        self.chk_edge_enabled.grid(row=1, column=0, sticky="w", padx=6, pady=4)

        box_act = ttk.Labelframe(tab_opts, text="Ações rápidas")
        box_act.grid(row=1, column=0, sticky="ew", padx=6, pady=6)
        box_act.columnconfigure(0, weight=1)
        ttk.Button(box_act, text="F1 • Ligar/Desligar controle", command=self._do_toggle_control).grid(row=0, column=0, sticky="ew", padx=6, pady=4)
        ttk.Button(box_act, text="F2 • Ligar/Desligar EdgeAccel", command=self._do_toggle_edge).grid(row=1, column=0, sticky="ew", padx=6, pady=4)
        ttk.Button(box_act, text="F4 • Recalibrar", command=self._do_recalib).grid(row=2, column=0, sticky="ew", padx=6, pady=4)

        # Rodapé de ações
        footer = ttk.Frame(root, padding=(10, 8))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(1, weight=1)

        ttk.Button(footer, text="Aplicar alterações", command=self._apply_all).grid(row=0, column=0, sticky="w")
        ttk.Label(footer, textvariable=self.var_status, style="Subtle.TLabel").grid(row=0, column=1, sticky="w", padx=10)
        ttk.Button(footer, text="Sincronizar do preset", command=self.sync_from_preset).grid(row=0, column=2, sticky="e", padx=(0, 6))
        ttk.Button(footer, text="Fechar", command=self._on_close).grid(row=0, column=3, sticky="e")

        # Dica extra
        tip = ttk.Label(root, text="Dica: Ajuste e depois grave no preset 'Personalizado' no seu código.", style="Subtle.TLabel")
        tip.grid(row=3, column=0, sticky="w", padx=12, pady=(0, 10))

    # ---------- helpers de layout ----------
    def _status_text(self, on: bool, is_control: bool) -> str:
        if is_control:
            return "Controle: pronto" if on else "Controle: indisponível"
        return "EdgeAccel: ligado" if on else "EdgeAccel: desligado"

    def _grid_of_scales(self, parent: ttk.Frame, items: List[tuple]):
        """Cria uma grade de linhas com: Label | Scale | Spinbox | valor"""
        parent.columnconfigure(1, weight=1)
        for r, (label, var, mn, mx, step, integer, tooltip) in enumerate(items):
            ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", padx=(8, 4), pady=4)

            scale = ttk.Scale(parent, from_=mn, to=mx, orient=tk.HORIZONTAL, variable=var)
            scale.grid(row=r, column=1, sticky="ew", padx=4, pady=4)

            if integer:
                spn = ttk.Spinbox(parent, from_=mn, to=mx, textvariable=var, increment=step, width=7)
            else:
                spn = ttk.Spinbox(parent, from_=mn, to=mx, textvariable=var, increment=step, format="%.3f", width=7)
            spn.grid(row=r, column=2, sticky="e", padx=(4, 8), pady=4)

            val_lbl = ttk.Label(parent, style="Value.TLabel")
            val_lbl.grid(row=r, column=3, sticky="e", padx=(0, 8))

            def _upd_label(*_, v=var, lbl=val_lbl, is_int=integer):
                try:
                    val = int(v.get()) if is_int else float(v.get())
                    lbl.configure(text=f"{val:d}" if is_int else f"{val:.3f}")
                except Exception:
                    pass

            var.trace_add("write", _upd_label)
            _upd_label()

            # Tooltips
            self._ToolTip(scale, tooltip)
            self._ToolTip(spn, tooltip)

    # ---------- eventos / ações ----------
    def _bind_shortcuts(self):
        self.root.bind("<F1>", lambda e: self._do_toggle_control())
        self.root.bind("<F2>", lambda e: self._do_toggle_edge())
        self.root.bind("<F4>", lambda e: self._do_recalib())

    def _on_preset_change(self, *_):
        try:
            idx = int(self.combo.current())
        except Exception:
            return
        self._apply_preset(idx)
        self.sync_from_preset()
        self._set_status("Preset aplicado e UI sincronizada.")

    def _do_toggle_control(self):
        if self._toggle_control:
            try:
                self._toggle_control()
                self._set_status("Controle alternado.")
            except Exception:
                self._set_status("Falha ao alternar controle.")

    def _reflect_edge_toggle(self):
        # Apenas atualiza os indicadores ao marcar/desmarcar o checkbox
        on = bool(self.var_edge_enabled.get())
        self.lbl_status_edge.configure(text=self._status_text(on, False), style=("Status.On.TLabel" if on else "Status.Off.TLabel"))

    def _do_toggle_edge(self):
        if self._toggle_edge:
            try:
                self._toggle_edge()
                # refletir estado atual pós-toggle vindo do core
                st = self._get_state()
                self.var_edge_enabled.set(bool(st["EDGE_ACCEL_ENABLED"]))
                self._reflect_edge_toggle()
                self._set_status("EdgeAccel alternado.")
            except Exception:
                self._set_status("Falha ao alternar EdgeAccel.")

    def _do_recalib(self):
        if self._request_recalibrate:
            try:
                self._request_recalibrate()
                self._set_status("Recalibração solicitada.")
            except Exception:
                self._set_status("Falha ao recalibrar.")

    def _apply_all(self):
        self.read_into_globals()
        self._set_status("Alterações aplicadas ao sistema.")

    def _set_status(self, text: str):
        self.var_status.set(text)
        # Retorna a mensagem "Pronto." após alguns segundos
        self.root.after(3000, lambda: self.var_status.set("Pronto."))

    # ---------- sincronização ----------
    def sync_from_preset(self):
        """Puxa o estado atual do core e empurra para os widgets."""
        try:
            self.combo.current(self._get_current_preset())
        except Exception:
            pass
        st = self._get_state()

        self.var_preset.set(str(self._get_current_preset()))
        self.var_deadzone.set(float(st["deadzone_deg"]))
        self.var_gain_yaw.set(float(st["gain_yaw"]))
        self.var_gain_pitch.set(float(st["gain_pitch"]))
        self.var_gain_power.set(float(st["gain_power"]))
        self.var_max_speed.set(int(st["max_speed_px"]))

        self.var_ema_alpha.set(float(st["ema_alpha"]))
        self.var_vel_ema_alpha.set(float(st["vel_ema_alpha"]))

        self.var_edge_margin.set(int(st["edge_margin"]))
        self.var_edge_max.set(float(st["edge_accel_max"]))
        self.var_edge_rate.set(float(st["edge_accel_rate"]))
        self.var_edge_decay.set(float(st["edge_decay_rate"]))

        self.var_yaw_strong_deg.set(float(st["yaw_strong_deg"]))
        self.var_yaw_strong_rate.set(float(st["yaw_strong_rate"]))

        self.var_invert_y.set(bool(st["INVERT_Y"]))
        self.var_edge_enabled.set(bool(st["EDGE_ACCEL_ENABLED"]))
        self._reflect_edge_toggle()

    def read_into_globals(self):
        """
        Lê os widgets e escreve no estado do core via set_state().
        Pode ser chamado a cada frame (ou no botão Aplicar).
        """
        st = self._get_state()
        st.update({
            "deadzone_deg":   float(self.var_deadzone.get()),
            "gain_yaw":       float(self.var_gain_yaw.get()),
            "gain_pitch":     float(self.var_gain_pitch.get()),
            "gain_power":     float(self.var_gain_power.get()),
            "max_speed_px":   int(self.var_max_speed.get()),
            "ema_alpha":      float(self.var_ema_alpha.get()),
            "vel_ema_alpha":  float(self.var_vel_ema_alpha.get()),
            "edge_margin":    int(self.var_edge_margin.get()),
            "edge_accel_max": float(self.var_edge_max.get()),
            "edge_accel_rate":float(self.var_edge_rate.get()),
            "edge_decay_rate":float(self.var_edge_decay.get()),
            "yaw_strong_deg": float(self.var_yaw_strong_deg.get()),
            "yaw_strong_rate":float(self.var_yaw_strong_rate.get()),
            "INVERT_Y":       bool(self.var_invert_y.get()),
            "EDGE_ACCEL_ENABLED": bool(self.var_edge_enabled.get()),
        })
        self._set_state(st)


# Dica de uso:
# Substitua a importação do arquivo antigo por este, mantendo a mesma assinatura
# de construção da classe TkHeadMouseUI. As funções/callbacks esperadas são as mesmas.
