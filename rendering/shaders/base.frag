#version 330
// Camera input pass: BGR -> RGB, basic grading, background dimming.
//#include common
uniform sampler2D u_cam;
uniform float u_show;       // 1 = show camera, 0 = black
uniform float u_dim;        // darken the camera image
uniform float u_contrast;
uniform float u_saturation;
uniform float u_brightness;
in vec2 v_uv;
out vec4 f_color;
void main() {
    vec3 c = texture(u_cam, v_uv).bgr;
    c = (c - 0.5) * u_contrast + 0.5 + u_brightness;
    c = sat_adjust(c, u_saturation);
    c = clamp(c, 0.0, 1.0) * (1.0 - u_dim) * u_show;
    f_color = vec4(c, 1.0);
}
