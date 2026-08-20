#!/usr/bin/env python3
"""Vektorove ilustracie pre explainer v2 - kreslene kodom, ziadne AI fotky.

Kazda funkcia vrati SVG string (viewBox 0 0 W H). Casti maju id s prefixom,
aby ich sablony mohli animovat po kusoch (assemble/pop/slide/draw).
Styl: hrube ink kontury (round join), plocha vypln, mierne zaoblenia -
sedi k Comic Neue / notes looku aj k tmavemu posteru (farby sa davaju parametrom).
"""


def _ink(S):
    return S["ink"]


def usb_port(S, p="up", w=520, h=390):
    """USB-A port celny pohlad: telo, otvor, jazycek so 4 kontaktmi."""
    ink = _ink(S)
    return f'''<svg id="{p}" viewBox="0 0 520 390" width="{w}" height="{h}">
<g id="{p}_body"><rect x="20" y="60" width="480" height="270" rx="26" fill="{S['card']}" stroke="{ink}" stroke-width="12"/></g>
<g id="{p}_hole"><rect x="70" y="120" width="380" height="150" rx="10" fill="#15151a" stroke="{ink}" stroke-width="10"/></g>
<g id="{p}_tongue"><rect x="92" y="196" width="336" height="52" rx="6" fill="#f6f6f2" stroke="{ink}" stroke-width="8"/>
<rect x="120" y="210" width="52" height="22" rx="4" fill="#c9a227"/><rect x="196" y="210" width="52" height="22" rx="4" fill="#c9a227"/>
<rect x="272" y="210" width="52" height="22" rx="4" fill="#c9a227"/><rect x="348" y="210" width="52" height="22" rx="4" fill="#c9a227"/></g>
<path id="{p}_glint" d="M 60 92 L 150 92" stroke="#ffffff" stroke-width="10" stroke-linecap="round" opacity="0.5"/>
</svg>'''


def usb_plug(S, p="pl", w=300, h=210):
    """USB-A konektor zboku (na zasunutie do portu)."""
    ink = _ink(S)
    return f'''<svg id="{p}" viewBox="0 0 300 210" width="{w}" height="{h}">
<rect x="10" y="40" width="150" height="130" rx="14" fill="#d8d8d2" stroke="{ink}" stroke-width="10"/>
<rect x="160" y="62" width="120" height="86" rx="8" fill="#eceae2" stroke="{ink}" stroke-width="10"/>
<rect x="196" y="84" width="60" height="18" rx="4" fill="#15151a"/>
<rect x="196" y="112" width="60" height="18" rx="4" fill="#15151a"/>
<path d="M 40 105 L 120 105" stroke="{ink}" stroke-width="8" stroke-linecap="round" opacity="0.35"/>
</svg>'''


def printer(S, p="pr", w=360, h=300):
    ink = _ink(S)
    return f'''<svg id="{p}" viewBox="0 0 360 300" width="{w}" height="{h}">
<g id="{p}_body"><rect x="30" y="90" width="300" height="130" rx="18" fill="{S['card']}" stroke="{ink}" stroke-width="11"/>
<circle cx="300" cy="125" r="9" fill="{S['accent2']}"/></g>
<g id="{p}_top"><rect x="90" y="40" width="180" height="60" rx="10" fill="#e7e5dc" stroke="{ink}" stroke-width="10"/></g>
<g id="{p}_paper"><rect x="105" y="205" width="150" height="70" rx="6" fill="#ffffff" stroke="{ink}" stroke-width="8"/>
<path d="M 125 228 L 235 228 M 125 250 L 210 250" stroke="#9a9a94" stroke-width="7" stroke-linecap="round"/></g>
<g id="{p}_slot"><rect x="95" y="196" width="170" height="14" rx="7" fill="#15151a"/></g>
</svg>'''


def keyboard(S, p="kb", w=380, h=240):
    ink = _ink(S)
    keys = ""
    for r, (y, n) in enumerate([(96, 8), (134, 8), (172, 6)]):
        xw = 280 / n
        for k in range(n):
            keys += (f'<rect x="{58 + k * xw + 4:.0f}" y="{y}" width="{xw - 9:.0f}" height="28" rx="6" '
                     f'fill="#f2f0e8" stroke="{ink}" stroke-width="6"/>')
    return f'''<svg id="{p}" viewBox="0 0 380 240" width="{w}" height="{h}">
<g id="{p}_body"><rect x="30" y="66" width="320" height="150" rx="16" fill="{S['card']}" stroke="{ink}" stroke-width="11"/></g>
<g id="{p}_keys">{keys}</g>
</svg>'''


def mouse(S, p="ms", w=260, h=300):
    ink = _ink(S)
    return f'''<svg id="{p}" viewBox="0 0 260 300" width="{w}" height="{h}">
<path id="{p}_cable" d="M 130 60 C 130 20 90 26 92 8" fill="none" stroke="{ink}" stroke-width="9" stroke-linecap="round"/>
<g id="{p}_body"><rect x="55" y="60" width="150" height="200" rx="72" fill="{S['card']}" stroke="{ink}" stroke-width="11"/>
<path d="M 130 60 L 130 150" stroke="{ink}" stroke-width="8"/>
<path d="M 55 150 L 205 150" stroke="{ink}" stroke-width="8"/></g>
<rect id="{p}_wheel" x="120" y="96" width="20" height="40" rx="10" fill="#d8d6cc" stroke="{ink}" stroke-width="7"/>
</svg>'''


def old_plug(S, p, kind, w=120, h=120):
    """Rozne stare konektory (kazde zariadenie malo iny) - DIN kruh / DB25 lichobeznik / PS2 stvorec."""
    ink = _ink(S)
    if kind == "din":
        inner = (f'<circle cx="60" cy="60" r="40" fill="#e9e7df" stroke="{ink}" stroke-width="9"/>'
                 f'<circle cx="45" cy="52" r="6" fill="{ink}"/><circle cx="75" cy="52" r="6" fill="{ink}"/>'
                 f'<circle cx="60" cy="74" r="6" fill="{ink}"/>')
    elif kind == "db25":
        inner = (f'<path d="M 18 42 L 102 42 L 92 78 L 28 78 Z" fill="#e9e7df" stroke="{ink}" stroke-width="9"/>'
                 + "".join(f'<circle cx="{34 + k * 13}" cy="55" r="4" fill="{ink}"/>' for k in range(5))
                 + "".join(f'<circle cx="{40 + k * 13}" cy="67" r="4" fill="{ink}"/>' for k in range(4)))
    else:  # ps2
        inner = (f'<rect x="24" y="24" width="72" height="72" rx="14" fill="#e9e7df" stroke="{ink}" stroke-width="9"/>'
                 f'<circle cx="60" cy="60" r="22" fill="#15151a"/><rect x="54" y="30" width="12" height="10" fill="{ink}"/>')
    return f'<svg id="{p}" viewBox="0 0 120 120" width="{w}" height="{h}">{inner}</svg>'


def smartphone(S, p="ph", w=220, h=380):
    ink = _ink(S)
    tiles = "".join(
        f'<rect x="{60 + (k % 3) * 36}" y="{150 + (k // 3) * 36}" width="30" height="30" rx="5" '
        f'fill="{["#8ecae6", "#ffb703", "#90be6d", "#f28482", "#b8b8ff", "#ffd166"][k]}" opacity="0.95"/>'
        for k in range(6))
    return f'''<svg id="{p}" viewBox="0 0 220 380" width="{w}" height="{h}">
<g id="{p}_body"><rect x="35" y="20" width="150" height="330" rx="26" fill="{S['card']}" stroke="{ink}" stroke-width="11"/>
<rect x="52" y="58" width="116" height="250" rx="8" fill="#f7f7f3" stroke="{ink}" stroke-width="6"/>
<circle cx="110" cy="40" r="6" fill="{ink}"/></g>
<g id="{p}_tiles">{tiles}</g>
<rect id="{p}_photo" x="60" y="150" width="30" height="30" rx="5" fill="#8ecae6" stroke="{ink}" stroke-width="4"/>
</svg>'''


def car_stereo(S, p="cs", w=460, h=250):
    ink = _ink(S)
    return f'''<svg id="{p}" viewBox="0 0 460 250" width="{w}" height="{h}">
<g id="{p}_body"><rect x="20" y="40" width="420" height="170" rx="16" fill="#20222a" stroke="{ink}" stroke-width="11"/></g>
<g id="{p}_disp"><rect x="150" y="66" width="250" height="52" rx="8" fill="#0e2a1e"/>
<path d="M 165 92 L 205 92 M 215 92 L 245 92 M 255 92 L 305 92" stroke="#37e08b" stroke-width="9" stroke-linecap="round"/></g>
<circle id="{p}_knob" cx="85" cy="125" r="38" fill="#3a3d47" stroke="{ink}" stroke-width="9"/>
<g id="{p}_usb"><rect x="150" y="140" width="86" height="40" rx="7" fill="#15151a" stroke="{S['accent']}" stroke-width="7"/>
<rect x="164" y="156" width="58" height="12" rx="3" fill="#f6f6f2"/></g>
<g id="{p}_btns">{"".join(f'<rect x="{258 + k * 48}" y="140" width="36" height="40" rx="7" fill="#3a3d47" stroke="{ink}" stroke-width="6"/>' for k in range(4))}</g>
</svg>'''


def mp3_player(S, p="m3", w=230, h=330):
    ink = _ink(S)
    return f'''<svg id="{p}" viewBox="0 0 230 330" width="{w}" height="{h}">
<g id="{p}_body"><rect x="45" y="30" width="140" height="270" rx="22" fill="{S['card']}" stroke="{ink}" stroke-width="11"/></g>
<rect id="{p}_scr" x="63" y="55" width="104" height="80" rx="8" fill="#123047"/>
<path d="M 100 80 L 100 110 L 128 95 Z" fill="#8ecae6"/>
<circle id="{p}_wheel" cx="115" cy="215" r="52" fill="#efede5" stroke="{ink}" stroke-width="9"/>
<circle cx="115" cy="215" r="18" fill="{S['card']}" stroke="{ink}" stroke-width="7"/>
</svg>'''


def crown(S, p="cr", w=200, h=140):
    return f'''<svg id="{p}" viewBox="0 0 200 140" width="{w}" height="{h}">
<path d="M 20 115 L 20 55 L 60 85 L 100 25 L 140 85 L 180 55 L 180 115 Z"
 fill="#ffd21f" stroke="{_ink(S)}" stroke-width="10" stroke-linejoin="round"/>
<circle cx="20" cy="48" r="10" fill="#ffd21f" stroke="{_ink(S)}" stroke-width="7"/>
<circle cx="100" cy="18" r="10" fill="#ffd21f" stroke="{_ink(S)}" stroke-width="7"/>
<circle cx="180" cy="48" r="10" fill="#ffd21f" stroke="{_ink(S)}" stroke-width="7"/>
</svg>'''


def stickman(S, p="sm", w=260, h=380, wave=True):
    ink = _ink(S)
    arm = ('<path id="%s_arm" d="M 130 205 C 165 190 185 160 192 128" fill="none" stroke="%s" stroke-width="12" stroke-linecap="round"/>'
           % (p, ink)) if wave else (
        '<path id="%s_arm" d="M 130 205 C 160 215 178 240 184 268" fill="none" stroke="%s" stroke-width="12" stroke-linecap="round"/>' % (p, ink))
    return f'''<svg id="{p}" viewBox="0 0 260 380" width="{w}" height="{h}">
<circle cx="130" cy="80" r="46" fill="none" stroke="{ink}" stroke-width="12"/>
<circle cx="114" cy="72" r="6" fill="{ink}"/><circle cx="146" cy="72" r="6" fill="{ink}"/>
<path d="M 112 96 A 24 24 0 0 0 148 96" fill="none" stroke="{ink}" stroke-width="8" stroke-linecap="round"/>
<path d="M 130 126 L 130 250" stroke="{ink}" stroke-width="12" stroke-linecap="round"/>
<path d="M 130 152 L 118 176 L 130 194 L 142 176 Z" fill="{ink}"/>
<path d="M 130 205 C 100 215 84 240 78 268" fill="none" stroke="{ink}" stroke-width="12" stroke-linecap="round"/>
{arm}
<path d="M 130 250 C 112 290 100 320 92 352" fill="none" stroke="{ink}" stroke-width="12" stroke-linecap="round"/>
<path d="M 130 250 C 148 290 160 320 168 352" fill="none" stroke="{ink}" stroke-width="12" stroke-linecap="round"/>
</svg>'''


def computer_tower(S, p="tw", w=250, h=320):
    """Stara PC skrina s TROMI roznymi portami (kruh/lichobeznik/stvorec) - kazdy kabel ma svoj."""
    ink = _ink(S)
    return f'''<svg id="{p}" viewBox="0 0 250 320" width="{w}" height="{h}">
<g id="{p}_body"><rect x="30" y="15" width="190" height="290" rx="18" fill="{S['card']}" stroke="{ink}" stroke-width="11"/>
<rect x="55" y="40" width="140" height="26" rx="6" fill="#e7e5dc" stroke="{ink}" stroke-width="7"/>
<rect x="55" y="80" width="140" height="12" rx="6" fill="#d8d6cc"/>
<circle cx="70" cy="272" r="9" fill="{S['accent2']}"/></g>
<g id="{p}_ports">
<circle id="{p}_p1" cx="90" cy="150" r="26" fill="#efede5" stroke="{ink}" stroke-width="8"/>
<circle cx="90" cy="150" r="10" fill="#15151a"/>
<path id="{p}_p2" d="M 135 190 L 205 190 L 197 216 L 143 216 Z" fill="#efede5" stroke="{ink}" stroke-width="8"/>
<rect id="{p}_p3" x="120" y="235" width="46" height="46" rx="8" fill="#efede5" stroke="{ink}" stroke-width="8"/>
<circle cx="143" cy="258" r="12" fill="#15151a"/>
</g></svg>'''


def music_note(S, p, w=70, h=90):
    ink = _ink(S)
    return f'''<svg id="{p}" viewBox="0 0 70 90" width="{w}" height="{h}">
<ellipse cx="22" cy="70" rx="16" ry="12" fill="{ink}"/>
<path d="M 36 70 L 36 14 L 60 8 L 60 26 L 40 31" fill="none" stroke="{ink}" stroke-width="9" stroke-linejoin="round"/>
</svg>'''


def stamp_badge(S, p, text, w=210, h=110):
    return f'''<svg id="{p}" viewBox="0 0 210 110" width="{w}" height="{h}">
<rect x="10" y="12" width="190" height="86" rx="14" fill="none" stroke="{S['accent2']}" stroke-width="9" transform="rotate(-7 105 55)"/>
<text x="105" y="72" text-anchor="middle" font-family="Main" font-size="46" font-weight="bold"
 fill="{S['accent2']}" transform="rotate(-7 105 55)">{text}</text>
</svg>'''
