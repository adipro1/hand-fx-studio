#version 330
// Generic reality-distortion pass: liquid field, point forces (bulge / pinch,
// swirl, ripple), expanding shockwaves and chromatic aberration.
//#include common
uniform sampler2D u_src;
uniform sampler2D u_field;
uniform float u_field_amt;
uniform vec4 u_pts[12];      // x, y (uv), radius (aspect units), strength
uniform int u_types[12];     // 0 bulge, 1 swirl, 2 ripple, 3 smear
uniform vec2 u_dirs[12];     // direction for smear
uniform int u_np;
uniform vec4 u_waves[8];     // x, y (uv), radius, amplitude
uniform int u_nw;
uniform float u_wave_width;
uniform float u_chroma;
uniform float u_ripple_freq;
in vec2 v_uv;
out vec4 f_color;

vec3 s(vec2 uv) { return texture(u_src, clamp(uv, vec2(0.0005), vec2(0.9995))).rgb; }

void main() {
    vec2 P = to_asp(v_uv);
    vec2 off = vec2(0.0);
    float energy = 0.0;
    if (u_field_amt > 0.0) {
        vec2 fv = texture(u_field, v_uv).xy * u_field_amt;
        off -= fv;
        energy += length(fv) * 6.0;
    }
    for (int i = 0; i < 12; i++) {
        if (i >= u_np) break;
        vec2 d = P - to_asp(u_pts[i].xy);
        float r = length(d);
        float R = u_pts[i].z;
        if (r >= R) continue;
        float f = 1.0 - r / R;
        f = f * f * (3.0 - 2.0 * f);
        float st = u_pts[i].w;
        int t = u_types[i];
        if (t == 0) {               // bulge (+) / pinch (-)
            off -= d * st * f;
            energy += abs(st) * f;
        } else if (t == 1) {        // swirl
            float a = st * f * f;
            off += rot2(a) * d - d;
            energy += abs(st) * f * 0.3;
        } else if (t == 2) {        // ripple
            float w = sin(r * u_ripple_freq / R - u_time * 8.0);
            off += (d / max(r, 1e-4)) * w * st * 0.02 * f;
            energy += abs(w) * abs(st) * f * 0.5;
        } else if (t == 3) {        // smear along direction
            off -= u_dirs[i] * st * f;
            energy += f * st * 4.0;
        }
    }
    for (int i = 0; i < 8; i++) {
        if (i >= u_nw) break;
        vec2 d = P - to_asp(u_waves[i].xy);
        float r = length(d);
        float k = (r - u_waves[i].z) / u_wave_width;
        float ring = exp(-k * k) * sign(k + 1e-4);
        off += (d / max(r, 1e-4)) * ring * u_waves[i].w;
        energy += abs(ring) * u_waves[i].w * 30.0;
    }
    vec2 suv = v_uv + vec2(off.x / u_aspect, off.y);
    vec3 c;
    if (u_chroma > 0.0) {
        vec2 ch = vec2(off.x / u_aspect, off.y) * u_chroma + vec2(0.0015, 0.0) * u_chroma * clamp(energy, 0.0, 1.0);
        c = vec3(s(suv + ch).r, s(suv).g, s(suv - ch).b);
    } else {
        c = s(suv);
    }
    f_color = vec4(c, 1.0);
}
