#version 330
// Instanced anti-aliased glowing line segments (capsules).
uniform vec2 u_res;
in vec2 a_corner;            // (-1|1, -1|1)
in vec4 i_seg;               // p0.xy, p1.xy (uv)
in vec4 i_col;               // rgb, opacity
in vec4 i_style;             // width px, glow px, additive 0/1, glow gain
out vec2 v_px;
flat out vec2 v_p0;
flat out vec2 v_p1;
flat out vec4 v_col;
flat out vec4 v_style;
void main() {
    vec2 p0 = i_seg.xy * u_res;
    vec2 p1 = i_seg.zw * u_res;
    vec2 d = p1 - p0;
    float L = length(d);
    vec2 dir = L > 1e-4 ? d / L : vec2(1.0, 0.0);
    vec2 nrm = vec2(-dir.y, dir.x);
    float ext = i_style.x * 0.5 + i_style.y * 3.5 + 1.5;
    vec2 pos = (a_corner.x < 0.0 ? p0 - dir * ext : p1 + dir * ext) + nrm * a_corner.y * ext;
    v_px = pos; v_p0 = p0; v_p1 = p1; v_col = i_col; v_style = i_style;
    gl_Position = vec4(pos / u_res * 2.0 - 1.0, 0.0, 1.0);
}
