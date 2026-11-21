#version 330
in vec4 v_col;
in float v_add;
out vec4 f_color;
void main() {
    f_color = vec4(v_col.rgb * v_col.a, v_col.a * (1.0 - v_add));
}
