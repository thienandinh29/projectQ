import { type ButtonHTMLAttributes } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

const variants = cva("button", {
  variants: {
    variant: {
      primary: "button-primary",
      secondary: "button-secondary",
      ghost: "button-ghost",
    },
  },
  defaultVariants: { variant: "primary" },
});
type Props = ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof variants>;
export function Button({
  className,
  variant,
  type = "button",
  ...props
}: Props) {
  return (
    <button
      type={type}
      className={twMerge(clsx(variants({ variant }), className))}
      {...props}
    />
  );
}
