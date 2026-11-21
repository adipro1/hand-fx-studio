#version 330
// Kaleidoscope centred on the hands. Segment count / rotation driven by gestures.
//#include common
uniform sampler2D u_src;
uniform vec2 u_center;     // uv
uniform float u_segments;
uniform float u_rotation;
uniform float u_zoom;
uniform float u_amount;    // 0..1 blend
uniform float u_radius;    // aspect units; <= 0 = fullscreen
uniform float u_hue;
in vec2 v_uv;
out vec4 f_color;
void main() {
    vec3 base = texture(u_src, v_uv).rgb;
    vec2 C = to_asp(u_center);
    vec2 d = to_asp(v_uv) - C;
    float r = length(d);
    float a = atan(d.y, d.x) + u_rotation;
    float seg = TAU / max(u_segments, 2.0);
    a = mod(a, seg);
    a = abs(a - seg * 0.5);
    vec2 q = C + vec2(cos(a), sin(a)) * r / u_zoom;
    vec2 suv = vec2(q.x / u_aspect, q.y);
    // mirror-repeat so we never sample outside the frame
    suv = abs(mod(suv + 1.0, 2.0) - 1.0);
    vec3 k = texture(u_src, suv).rgb;
    if (u_hue != 0.0) k = hue_shift(k, u_hue * r);
    float m = u_amount;
    if (u_radius > 0.0) m *= 1.0 - smoothstep(u_radius * 0.75, u_radius, r);
    f_color = vec4(mix(base, k, m), 1.0);
}
