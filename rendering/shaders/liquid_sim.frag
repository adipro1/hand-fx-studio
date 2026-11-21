#version 330
// Persistent liquid displacement field. Fingertips inject their velocity; the
// field advects itself, diffuses and decays -> viscous, trailing liquid motion.
//#include common
uniform sampler2D u_prev;
uniform vec4 u_splat[12];     // x, y (uv), radius (aspect units), strength
uniform vec2 u_splat_vel[12]; // velocity (aspect units / s)
uniform int u_ns;
uniform float u_dt;
uniform float u_decay;        // fraction kept per second
uniform float u_advect;
uniform float u_turbulence;
in vec2 v_uv;
out vec4 f_color;
void main() {
    vec2 texel = 1.0 / u_res;
    vec2 cur = texture(u_prev, v_uv).xy;
    // semi-Lagrangian self-advection
    vec2 back = v_uv - vec2(cur.x / u_aspect, cur.y) * u_advect * u_dt * 4.0;
    vec2 f = texture(u_prev, back).xy;
    // light diffusion
    vec2 n = texture(u_prev, back + vec2(texel.x, 0)).xy + texture(u_prev, back - vec2(texel.x, 0)).xy
           + texture(u_prev, back + vec2(0, texel.y)).xy + texture(u_prev, back - vec2(0, texel.y)).xy;
    f = mix(f, n * 0.25, 0.25);
    // swirl turbulence keeps the liquid alive
    if (u_turbulence > 0.0) {
        float a = fbm(v_uv * 4.0 + u_time * 0.15) * TAU * 2.0;
        f += vec2(cos(a), sin(a)) * length(f) * u_turbulence * u_dt * 3.0;
    }
    f *= pow(u_decay, u_dt);
    vec2 P = to_asp(v_uv);
    for (int i = 0; i < 12; i++) {
        if (i >= u_ns) break;
        vec2 d = P - to_asp(u_splat[i].xy);
        float r = u_splat[i].z;
        float g = exp(-dot(d, d) / (r * r));
        f += u_splat_vel[i] * g * u_splat[i].w * u_dt;
    }
    float m = length(f);
    if (m > 0.25) f *= 0.25 / m;
    f_color = vec4(f, 0.0, 1.0);
}
