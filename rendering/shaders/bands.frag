#version 330
// Finger Bands (reference 03): strips between matching fingertips of both hands,
// each strip rendered with its own filter.
//#include common
uniform sampler2D u_src;
//#include filters

in vec2 v_uv;
out vec4 f_color;

uniform vec2 u_quads[16];   // 4 bands x 4 vertices
uniform int u_modes[4];
uniform float u_alive[4];   // per band fade 0..1
uniform int u_nb;
uniform float u_amount;
uniform float u_cell;
uniform vec3 u_c1;
uniform vec3 u_c2;
uniform vec3 u_line_col;
uniform float u_line_w;

void main() {
    vec2 uv = v_uv;
    vec3 base = src(uv);
    vec3 col = base;
    float edge = 0.0;
    for (int b = 0; b < 4; b++) {
        if (b >= u_nb) break;
        vec2 v[8];
        for (int i = 0; i < 8; i++) v[i] = u_quads[b * 4 + (i < 4 ? i : 3)];
        float d = sd_poly(uv, v, 4) * u_res.y;
        float inside = (1.0 - smoothstep(-0.75, 0.75, d)) * u_alive[b];
        if (inside > 0.0) {
            vec3 c1 = u_c1, c2 = u_c2;
            int m = u_modes[b];
            if (m == F_EDGES) c1 = vec3(1.0);
            vec3 fc = apply_filter(m, uv, u_amount, u_cell, c1, c2);
            col = mix(col, fc, inside);
        }
        if (u_line_w > 0.0)
            edge = max(edge, (1.0 - smoothstep(u_line_w * 0.5 - 0.6, u_line_w * 0.5 + 0.6, abs(d))) * u_alive[b]);
    }
    col = mix(col, u_line_col, edge);
    f_color = vec4(col, 1.0);
}
