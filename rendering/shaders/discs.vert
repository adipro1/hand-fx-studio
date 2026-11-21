#version 330
// Instanced discs / rings / soft particles.
uniform vec2 u_res;
in vec2 a_corner;
in vec4 i_circ;              // x, y (uv), radius px, ring thickness px (0 = filled)
in vec4 i_col;
in vec3 i_style;             // glow px, additive, softness (0 hard edge .. 1 gaussian)
out vec2 v_px;
flat out vec4 v_circ;
flat out vec4 v_col;
flat out vec3 v_style;
void main() {
    vec2 c = i_circ.xy * u_res;
    float ext = i_circ.z + i_circ.w * 0.5 + i_style.x * 3.5 + 1.5;
    vec2 pos = c + a_corner * ext;
    v_px = pos; v_circ = vec4(c, i_circ.zw); v_col = i_col; v_style = i_style;
    gl_Position = vec4(pos / u_res * 2.0 - 1.0, 0.0, 1.0);
}
