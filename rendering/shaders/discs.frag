#version 330
in vec2 v_px;
flat in vec4 v_circ;
flat in vec4 v_col;
flat in vec3 v_style;
out vec4 f_color;
void main() {
    float d = length(v_px - v_circ.xy);
    float r = v_circ.z;
    float sd = v_circ.w > 0.0 ? abs(d - r) - v_circ.w * 0.5 : d - r;
    float core;
    if (v_style.z > 0.0 && v_circ.w <= 0.0) {
        float g = exp(-(d * d) / max(r * r, 1e-4) * 2.2);
        core = mix(1.0 - smoothstep(-0.7, 0.7, sd), g, v_style.z);
    } else {
        core = 1.0 - smoothstep(-0.7, 0.7, sd);
    }
    float glow = v_style.x > 0.0 ? exp(-max(sd, 0.0) / v_style.x) * 0.55 : 0.0;
    float a = v_col.a;
    f_color = vec4(v_col.rgb * (core + glow * (1.0 - core)) * a, core * a * (1.0 - v_style.y));
}
