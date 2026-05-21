import { z } from "zod";

export const budgetSchema = z.object({
  monthlyLimit: z.string().refine((val) => val.trim() === "" || (!isNaN(Number(val)) && Number(val) >= 0), {
    message: "Monthly limit must be a non-negative number",
  }),
  threshold: z.string().refine((val) => val.trim() !== "" && !isNaN(Number(val)) && Number(val) >= 0 && Number(val) <= 100, {
    message: "Threshold must be between 0 and 100",
  }),
});

export type BudgetFormData = z.infer<typeof budgetSchema>;

export const passwordChangeSchema = z
  .object({
    currentPassword: z.string().min(1, "Current password is required"),
    newPassword: z.string().min(8, "New password must be at least 8 characters"),
    confirmPassword: z.string().min(1, "Please confirm your new password"),
  })
  .refine((data) => data.newPassword === data.confirmPassword, {
    message: "New passwords do not match",
    path: ["confirmPassword"],
  });

export type PasswordChangeFormData = z.infer<typeof passwordChangeSchema>;

export const loginSchema = z.object({
  email: z.string().min(1, "Email is required").email("Invalid email address"),
  password: z.string().min(1, "Password is required"),
});

export type LoginFormData = z.infer<typeof loginSchema>;

export const registerSchema = z
  .object({
    email: z
      .string()
      .min(1, "Email is required")
      .email("Please enter a valid email address"),
    password: z
      .string()
      .min(8, "Password must be at least 8 characters")
      .regex(/[A-Z]/, "Must contain at least one uppercase letter")
      .regex(/[a-z]/, "Must contain at least one lowercase letter")
      .regex(/[0-9]/, "Must contain at least one number"),
    confirm_password: z.string().min(1, "Please confirm your password"),
  })
  .refine((data) => data.password === data.confirm_password, {
    message: "Passwords do not match",
    path: ["confirm_password"],
  });

export type RegisterFormData = z.infer<typeof registerSchema>;

export const forgotPasswordSchema = z.object({
  email: z.string().min(1, "Email is required").email("Invalid email address"),
});

export type ForgotPasswordFormData = z.infer<typeof forgotPasswordSchema>;

export const resetPasswordSchema = z.object({
  password: z.string().min(8, "Password must be at least 8 characters"),
});

export type ResetPasswordFormData = z.infer<typeof resetPasswordSchema>;

export const callsFilterSchema = z.object({
  status: z.string(),
  model: z.string(),
  user_id: z.string(),
  call_type: z.string(),
  agent_name: z.string(),
  date_from: z.string(),
  date_to: z.string(),
  sort_by: z.enum(["created_at", "cost_usd", "total_tokens", "latency_ms"]),
  sort_order: z.enum(["asc", "desc"]),
});

export type CallsFilterFormData = z.infer<typeof callsFilterSchema>;

export const apiKeySchema = z.object({
  name: z.string().min(1, "Key name is required"),
});

export type ApiKeyFormData = z.infer<typeof apiKeySchema>;

export const onboardingTriggerSchema = z.object({
  category: z.enum(["TOKEN_OVERFLOW", "RATE_LIMIT", "AUTH_FAILURE", "LOOP_DETECTED", "COST_SPIKE"]),
});

export type OnboardingTriggerFormData = z.infer<typeof onboardingTriggerSchema>;

export const prGenerationSchema = z.object({
  repositoryOwner: z.string(),
  repositoryName: z.string(),
  baseBranch: z.string(),
});

export type PrGenerationFormData = z.infer<typeof prGenerationSchema>;
