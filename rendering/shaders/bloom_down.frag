#version 330
// Downsample (4 bilinear taps) with soft threshold for bloom.
uniform sampler2D u_src;
uniform vec2 u_texel;      // source texel size
uniform float u_threshold;
in vec2 v_uv;
out vec4 f_color;
void main() {
    vec4 c = texture(u_src, v_uv + u_texel * vec2(-1, -1)) + texture(u_src, v_uv + u_texel * vec2(1, -1))
           + texture(u_src, v_uv + u_texel * vec2(-1, 1)) + texture(u_src, v_uv + u_texel * vec2(1, 1));
    c *= 0.25;
    float b = max(c.r, max(c.g, c.b));
    float k = max(b - u_threshold, 0.0) / max(b, 1e-4);
    f_color = vec4(c.rgb * k, 1.0);
}
