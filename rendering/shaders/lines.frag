#version 330
in vec2 v_px;
flat in vec2 v_p0;
flat in vec2 v_p1;
flat in vec4 v_col;
flat in vec4 v_style;
out vec4 f_color;
void main() {
    vec2 e = v_p1 - v_p0;
    vec2 w = v_px - v_p0;
    float t = clamp(dot(w, e) / max(dot(e, e), 1e-6), 0.0, 1.0);
    float d = length(w - e * t);
    float hw = v_style.x * 0.5;
    float core = 1.0 - smoothstep(hw - 0.7, hw + 0.7, d);
    float glow = v_style.y > 0.0 ? exp(-max(d - hw, 0.0) / v_style.y) * 0.55 * v_style.w : 0.0;
    float a = v_col.a;
    f_color = vec4(v_col.rgb * (core + glow * (1.0 - core)) * a, core * a * (1.0 - v_style.z));
}
