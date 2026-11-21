#version 330
// Final composite: scene + premultiplied overlay + bloom, soft highlight roll-off.
uniform sampler2D u_scene;
uniform sampler2D u_overlay;
uniform sampler2D u_bloom1;
uniform sampler2D u_bloom2;
uniform float u_bloom;
uniform float u_vignette;
in vec2 v_uv;
out vec4 f_color;
void main() {
    vec3 s = texture(u_scene, v_uv).rgb;
    vec4 o = texture(u_overlay, v_uv);
    vec3 c = s * (1.0 - clamp(o.a, 0.0, 1.0)) + o.rgb;
    c += (texture(u_bloom1, v_uv).rgb * 0.5 + texture(u_bloom2, v_uv).rgb * 0.7) * u_bloom;
    // soft shoulder: keeps neon cores white-hot without harsh clipping
    vec3 over = max(c - 0.8, 0.0);
    c = min(c, 0.8) + over / (1.0 + over * 2.5);
    c = c * 1.0 / 0.97;
    if (u_vignette > 0.0) {
        vec2 d = v_uv - 0.5;
        c *= 1.0 - u_vignette * dot(d, d) * 1.6;
    }
    f_color = vec4(clamp(c, 0.0, 1.0), 1.0);
}
