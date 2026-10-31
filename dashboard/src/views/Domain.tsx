import { useParams } from "react-router";
import { DOMAIN_NAME, isDomain } from "../lib/levels";
import { PageTitle } from "./placeholders";

export default function Domain() {
  const { name } = useParams();
  if (!isDomain(name)) {
    return (
      <section>
        <PageTitle>Domain not found</PageTitle>
        <p className="mt-2 text-muted">There is no domain called “{name}”.</p>
      </section>
    );
  }
  return <PageTitle>{DOMAIN_NAME[name]}</PageTitle>;
}
