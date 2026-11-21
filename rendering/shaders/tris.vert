#version 330
in vec2 a_pos;               // uv
in vec4 a_col;               // rgb, opacity
in float a_add;
out vec4 v_col;
out float v_add;
void main() {
    v_col = a_col; v_add = a_add;
    gl_Position = vec4(a_pos * 2.0 - 1.0, 0.0, 1.0);
}
