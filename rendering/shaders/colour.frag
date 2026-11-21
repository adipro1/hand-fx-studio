#version 330
// Colour transformations: psychedelic hue flow, hue shift, saturation,
// contrast, posterise, negative zones around hands, RGB displacement.
//#include common
uniform sampler2D u_src;
uniform float u_hue;          // global hue rotation 0..1
uniform float u_flow;         // psychedelic hue flow amount
uniform float u_saturation;
uniform float u_contrast;
uniform float u_posterize;    // 0 = off, else levels
uniform float u_rgb_shift;    // RGB displacement amount (uv)
uniform vec2 u_rgb_dir;
uniform vec4 u_zones[4];      // x, y (uv), radius (aspect), strength: invert zones
uniform int u_nz;
uniform float u_zone_mode;    // 0 invert, 1 hue-rotate, 2 thermal
uniform float u_amount;       // global effect mix
uniform float u_local;        // 1 = effect only near hands (uses zones as mask)
in vec2 v_uv;
out vec4 f_color;
void main() {
    vec2 o = u_rgb_dir * u_rgb_shift;
    vec3 orig = texture(u_src, v_uv).rgb;
    vec3 c = vec3(texture(u_src, v_uv + o).r, texture(u_src, v_uv).g, texture(u_src, v_uv - o).b);
    vec2 P = to_asp(v_uv);
    if (u_flow > 0.0) {
        float l = luma(c);
        float h = l * 1.5 + fbm(P * 2.5 + u_time * 0.2) * 1.2 + u_time * 0.08;
        vec3 psy = hsv2rgb(vec3(fract(h), 0.85, clamp(l * 1.3 + 0.1, 0.0, 1.0)));
        c = mix(c, psy, u_flow);
    }
    if (u_hue != 0.0) c = hue_shift(c, u_hue);
    c = sat_adjust(c, u_saturation);
    c = (c - 0.5) * u_contrast + 0.5;
    if (u_posterize > 1.5) c = floor(c * u_posterize + 0.5) / u_posterize;
    c = clamp(c, 0.0, 1.0);

    float mask = 0.0;
    for (int i = 0; i < 4; i++) {
        if (i >= u_nz) break;
        float r = length(P - to_asp(u_zones[i].xy));
        mask = max(mask, (1.0 - smoothstep(u_zones[i].z * 0.8, u_zones[i].z, r)) * u_zones[i].w);
    }
    if (u_local > 0.5) {
        c = mix(orig, c, mask);
    } else if (u_nz > 0) {
        vec3 z;
        if (u_zone_mode < 0.5) z = 1.0 - c;
        else if (u_zone_mode < 1.5) z = hue_shift(c, 0.5);
        else z = jet(luma(c));
        c = mix(c, z, mask);
    }
    f_color = vec4(mix(orig, c, u_amount), 1.0);
}
