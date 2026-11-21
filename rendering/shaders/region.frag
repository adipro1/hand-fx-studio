#version 330
// Polygon region filter (Filter Frame / Glass Prism / Tracking HUD).
// Applies a stylised filter inside a polygon defined by fingertips.
//#include common
uniform sampler2D u_src;
//#include filters

in vec2 v_uv;
out vec4 f_color;

uniform vec2 u_poly[8];
uniform int u_n;
uniform int u_mode;
uniform float u_amount;
uniform float u_cell;        // pixel cell size for halftone / pixel modes
uniform vec3 u_c1;
uniform vec3 u_c2;
uniform float u_mix;         // 0..1 fade in
uniform vec3 u_outline_col;
uniform float u_outline_w;   // px, 0 = none
uniform int u_stepped;       // 1 = outline/mask follows pixel grid (pixel mode)
uniform float u_refract;     // lens zoom inside the region (0 = none)
uniform float u_chroma;      // chromatic split on refraction
uniform float u_outside_dim;
uniform vec3 u_outside_tint;
uniform float u_outside_tint_amt;
uniform vec2 u_centroid;

float inside_at(vec2 uv) {
    vec2 v[8];
    for (int i = 0; i < 8; i++) v[i] = u_poly[i];
    return sd_poly(uv, v, u_n) < 0.0 ? 1.0 : 0.0;
}

void main() {
    vec2 uv = v_uv;
    vec3 base = src(uv);
    if (u_n < 3) { f_color = vec4(base, 1.0); return; }

    vec2 v[8];
    for (int i = 0; i < 8; i++) v[i] = u_poly[i];
    float d = sd_poly(uv, v, u_n) * u_res.y;   // signed distance in pixels
    float inside;
    float edge = 0.0;

    if (u_stepped == 1) {
        float b = u_cell * 2.2;
        vec2 px = uv * u_res;
        vec2 cell = floor(px / b);
        vec2 cc = (cell + 0.5) * b / u_res;
        inside = inside_at(cc);
        if (u_outline_w > 0.0) {
            vec2 f = px - cell * b;   // position inside block
            vec2 o = b / u_res;
            float w = u_outline_w;
            float l = inside_at(cc - vec2(o.x, 0.0)), r = inside_at(cc + vec2(o.x, 0.0));
            float t = inside_at(cc - vec2(0.0, o.y)), bo = inside_at(cc + vec2(0.0, o.y));
            if (inside > 0.5) {
                edge = max(edge, (l < 0.5 && f.x < w) ? 1.0 : 0.0);
                edge = max(edge, (r < 0.5 && f.x > b - w) ? 1.0 : 0.0);
                edge = max(edge, (t < 0.5 && f.y < w) ? 1.0 : 0.0);
                edge = max(edge, (bo < 0.5 && f.y > b - w) ? 1.0 : 0.0);
            }
        }
    } else {
        inside = 1.0 - smoothstep(-0.75, 0.75, d);
        if (u_outline_w > 0.0) {
            edge = 1.0 - smoothstep(u_outline_w * 0.5 - 0.6, u_outline_w * 0.5 + 0.6, abs(d));
        }
    }

    // outside grade
    vec3 outside = base * (1.0 - u_outside_dim);
    outside = mix(outside, outside * u_outside_tint * 1.4, u_outside_tint_amt);

    vec3 col = outside;
    if (inside > 0.0) {
        vec2 suv = uv;
        int mode = u_mode;
        if (u_refract > 0.0) suv = u_centroid + (uv - u_centroid) / (1.0 + u_refract);
        if (mode == F_MIRROR) { suv.x = 2.0 * u_centroid.x - suv.x; mode = F_NONE; }
        vec3 fc;
        if (u_chroma > 0.0) {
            vec2 dir = (uv - u_centroid) * u_chroma;
            fc.r = apply_filter(mode, suv + dir, u_amount, u_cell, u_c1, u_c2).r;
            fc.g = apply_filter(mode, suv, u_amount, u_cell, u_c1, u_c2).g;
            fc.b = apply_filter(mode, suv - dir, u_amount, u_cell, u_c1, u_c2).b;
        } else {
            fc = apply_filter(mode, suv, u_amount, u_cell, u_c1, u_c2);
        }
        col = mix(outside, mix(base, fc, u_mix), inside);
    }
    col = mix(col, u_outline_col, edge * u_mix);
    f_color = vec4(col, 1.0);
}
