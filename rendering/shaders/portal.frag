#version 330
// Portals: a swirling tunnel into a transformed version of the world.
//#include common
uniform sampler2D u_src;
uniform vec4 u_portals[2];    // x, y (uv), radius (aspect units), open 0..1
uniform float u_spin[2];      // rotation (radians)
uniform int u_np;
uniform int u_style;          // 0 vortex tunnel, 1 kaleido world, 2 inverted dimension, 3 thermal dimension
uniform float u_twist;
uniform float u_lens;         // gravitational lensing strength outside the rim
uniform vec3 u_tint;
in vec2 v_uv;
out vec4 f_color;

vec3 s(vec2 uv) { return texture(u_src, abs(mod(uv + 1.0, 2.0) - 1.0)).rgb; }

void main() {
    vec2 P = to_asp(v_uv);
    vec2 suv = v_uv;
    vec3 col = vec3(0.0);
    bool done = false;
    for (int i = 0; i < 2; i++) {
        if (i >= u_np || done) break;
        vec4 pt = u_portals[i];
        float R = pt.z * pt.w;
        if (R < 1e-4) continue;
        vec2 C = to_asp(pt.xy);
        vec2 d = P - C;
        float r = length(d);
        if (r < R) {
            float rn = r / R;
            float a = atan(d.y, d.x);
            vec3 c;
            if (u_style == 0) {
                // vortex tunnel: depth from radius, twist increases towards centre
                float depth = 0.35 / max(rn, 0.04);
                float ang = a + u_spin[i] + u_twist * (1.0 - rn) * (1.0 - rn) * 4.0;
                vec2 q = vec2(ang / TAU * 3.0, depth + u_time * 0.6);
                vec2 tuv = vec2(fract(q.x), fract(q.y * 0.5));
                c = s(tuv);
                c = hue_shift(c, q.y * 0.15) * (0.25 + 0.95 * smoothstep(0.0, 0.6, rn));
            } else if (u_style == 1) {
                float seg = TAU / 8.0;
                float aa = mod(a + u_spin[i], seg);
                aa = abs(aa - seg * 0.5);
                vec2 q = C + vec2(cos(aa), sin(aa)) * r * 1.4;
                c = hue_shift(s(vec2(q.x / u_aspect, q.y)), u_time * 0.1 + rn * 0.5);
            } else if (u_style == 2) {
                vec2 q = C + rot2(u_spin[i] * 0.5) * d * (0.7 + 0.3 * rn);
                c = 1.0 - s(vec2(q.x / u_aspect, q.y));
            } else {
                vec2 q = C + rot2(u_spin[i] * 0.3) * d;
                c = jet(luma(s(vec2(q.x / u_aspect, q.y))));
            }
            c = mix(c, c * u_tint * 1.5, 0.25);
            float edge = smoothstep(0.85, 1.0, rn);
            col = mix(c, s(v_uv), edge * 0.3);
            done = true;
        } else if (u_lens > 0.0 && r < R * 2.0) {
            // light bending around the rim
            float k = 1.0 - (r - R) / R;
            vec2 rot = rot2(k * k * u_lens * 0.8) * d;
            vec2 q = C + rot * (1.0 - k * k * u_lens * 0.15);
            suv = vec2(q.x / u_aspect, q.y);
        }
    }
    if (!done) col = s(suv);
    f_color = vec4(col, 1.0);
}
