import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Button } from "./Button";

describe("Button", () => {
  it("calls onClick when clicked", () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Run Producer</Button>);

    fireEvent.click(screen.getByRole("button", { name: "Run Producer" }));

    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("is disabled and unclickable while isLoading", () => {
    const onClick = vi.fn();
    render(
      <Button onClick={onClick} isLoading>
        Run Producer
      </Button>,
    );

    const button = screen.getByRole("button", { name: "Run Producer" });
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("respects an explicit disabled prop", () => {
    render(<Button disabled>Run Director</Button>);
    expect(screen.getByRole("button", { name: "Run Director" })).toBeDisabled();
  });
});
