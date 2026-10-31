import { render, screen } from "@testing-library/react";
import App from "../src/App";

describe("scaffold", () => {
  it("renders the app title and the prototype disclaimer", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "Crew Context Monitor" })).toBeInTheDocument();
    expect(screen.getByText(/not a medical device/i)).toBeInTheDocument();
  });
});
