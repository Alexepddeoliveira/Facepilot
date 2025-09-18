# FacePilot

**FacePilot** é um head‑tracker leve que usa a webcam para transformar seus movimentos de cabeça em **controle de câmera 360°** no PC — com presets de sensibilidade, aceleração lateral estilo controle e **recalibração rápida** via cruz verde. Ideal para jogar sem usar as mãos.

---

## Recursos

* **Controle de câmera 360°** em jogos e apps.
* **Aceleração lateral (EdgeAccelX)** inspirada em thumbstick, para continuar girando mesmo ao encostar na borda.
* **Suavidade e precisão**: zona morta, curva não‑linear e dupla suavização (ângulos e velocidade).
* **Presets prontos** (Precisão, Equilíbrio, Rápido) + modo **Personalizado**.
* **Hotkeys globais** (funcionam fora da janela do app).
* ✳**Recalibração rápida** (F4) com **cruz verde** na tela.
* **Failsafe**: mover o mouse para (0,0) cancela via PyAutoGUI.
* **100% local**: nenhum dado sai da sua máquina.

---

## Requisitos

* **Python 3.9+**
* Webcam
* Sistemas: **Windows** (recomendado), macOS, Linux

### Dependências Python

```bash
python -m pip install --upgrade opencv-python mediapipe pyautogui keyboard pydirectinput
```

> *Windows*: o FacePilot usa automaticamente um backend **RAW (SendInput)** para movimento relativo puro; `pydirectinput` é recomendado como fallback. Em macOS/Linux, o controle funciona com PyAutoGUI (e hotkeys podem exigir permissões de acessibilidade/sudo).

---

## Como executar

```bash
python facepilot.py
```

1. Ao abrir, olhe para o **centro da tela** (cruz verde) para a calibração inicial.
2. Pressione **F1** para ativar/desativar o controle.
3. Troque a “pegada” com **F3** / **Shift+F3** (presets).
4. Se o centro “derivar”, use **F4** para recalibrar (a cruz aparece, some ao fim).

---

## Atalhos (globais)

* **F1** – Liga/Desliga o controle
* **F2** – Liga/Desliga **EdgeAccelX** (aceleração lateral)
* **F3** / **Shift+F3** – Próximo/Anterior **Preset**
* **F4** – **Recalibrar** (exibe cruz verde)
* **ESC** – Sair (quando a janela do vídeo está em foco)

---

## Presets e ajustes finos

Abra o arquivo e edite o bloco `PRESETS` para ajustar facilmente:

* `deadzone_deg` ↑ → menos tremor; ↓ → mais responsivo
* `gain_yaw` / `gain_pitch` ↑ → mais sensível
* `gain_power` (≥ 1.0) → curva não‑linear (1.0 = linear)
* `max_speed_px` → limite de velocidade por frame
* `ema_alpha` / `vel_ema_alpha` → suavização (quanto menor, mais suave)
* `edge_margin`, `edge_accel_max`, `edge_accel_rate`, `edge_decay_rate` → “força” e resposta da aceleração na borda

> Dica: comece no preset **Equilíbrio** e ajuste `gain_yaw` e `deadzone_deg` conforme o jogo.

---

## Como funciona (resumo técnico)

* **MediaPipe FaceMesh** estima yaw/pitch/roll da cabeça em tempo real.
* Um pipeline converte ângulos → velocidade (px/frame) com **zona morta** + **curva de ganho** + **clamps**.
* **Aceleração estilo stick** no eixo X acumula “boost” enquanto você empurra na borda ou mantém yaw forte.
* Backend de entrada:

  * **Windows RAW (SendInput)** → `MOUSEEVENTF_MOVE` (relativo puro)
  * **PyDirectInput** (fallback recomendado no Windows)
  * **PyAutoGUI** (fallback universal)

---

## Solução de problemas

* **Backend aparece como PyAutoGUI no HUD no Windows**: confirme que está rodando com o Python correto e/ou como **Administrador**; instale `pydirectinput`. Alguns jogos requerem privilégios iguais (jogo em admin → Python em admin).
* **Hotkeys não funcionam no macOS**: conceda permissão de **Acessibilidade** ao Terminal/IDE nas Preferências do Sistema.
* **Trepidação**: aumente `deadzone_deg` e/ou reduza `gain_*`. Ajuste `ema_alpha`/`vel_ema_alpha` para suavizar.
* **Giro lento**: aumente `gain_yaw` e `max_speed_px`. Para borda, ajuste `edge_accel_max`/`edge_accel_rate`.
* **Anticheat**: alguns jogos com anti‑cheat rigoroso podem bloquear input simulado. Use com cautela.

---

## Compatibilidade

* **Windows 10/11**: melhor experiência (RAW + DirectInput).
* **macOS/Linux**: funciona com PyAutoGUI; hotkeys globais podem requerer permissões adicionais.

---

## Licença

MIT — sinta‑se livre para usar, modificar e contribuir.

---

## Créditos

* Rastreamento facial: **MediaPipe FaceMesh**
* Input: **SendInput (Windows)**, **PyDirectInput**, **PyAutoGUI**

---

> Dúvidas, feedbacks, ideias de presets para jogos específicos? Abra uma issue ou mande mensagem. 🎮
