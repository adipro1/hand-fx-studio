#version 330
// Separable 9-tap gaussian (linear sampling trick -> effectively 17 taps).
uniform sampler2D u_src;
uniform vec2 u_dir;        // texel step * direction
in vec2 v_uv;
out vec4 f_color;
void main() {
    const float w0 = 0.2270270270, w1 = 0.3162162162, w2 = 0.0702702703;
    const float o1 = 1.3846153846, o2 = 3.2307692308;
    vec3 c = texture(u_src, v_uv).rgb * w0;
    c += texture(u_src, v_uv + u_dir * o1).rgb * w1 + texture(u_src, v_uv - u_dir * o1).rgb * w1;
    c += texture(u_src, v_uv + u_dir * o2).rgb * w2 + texture(u_src, v_uv - u_dir * o2).rgb * w2;
    f_color = vec4(c, 1.0);
}
