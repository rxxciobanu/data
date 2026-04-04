import { z } from "zod";

export const loginSchema = z.object({
  email: z.string().email("Invalid email address"),
  password: z.string().min(1, "Password is required"),
});

export const registerSchema = z.object({
  email: z.string().email("Invalid email address"),
  password: z
    .string()
    .min(8, "Password must be at least 8 characters")
    .regex(/[A-Z]/, "Password must contain an uppercase letter")
    .regex(/[0-9]/, "Password must contain a number"),
});

export const preferencesSchema = z.object({
  alert_threshold: z.number().min(0).max(1),
  alert_enabled: z.boolean(),
  bankroll: z.number().min(0),
  kelly_fraction: z.number().min(0.01).max(1),
  max_bet_pct: z.number().min(0.01).max(1),
  max_total_exposure: z.number().min(0.01).max(1),
  min_bet_size: z.number().min(0),
});

export const whaleConfigSchema = z.object({
  whale_enabled: z.boolean(),
  whale_min_trade_size: z.number().min(0),
  whale_extra_wallets: z.array(
    z.object({
      address: z.string().min(1, "Address is required"),
      label: z.string(),
    })
  ),
});

export const apiKeySchema = z.object({
  label: z.string().min(1, "Label is required").max(100),
});

export type LoginForm = z.infer<typeof loginSchema>;
export type RegisterForm = z.infer<typeof registerSchema>;
export type PreferencesForm = z.infer<typeof preferencesSchema>;
export type WhaleConfigForm = z.infer<typeof whaleConfigSchema>;
export type ApiKeyForm = z.infer<typeof apiKeySchema>;
