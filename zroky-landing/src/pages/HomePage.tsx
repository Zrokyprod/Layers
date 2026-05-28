import Hero from '../components/Hero';
import Proof from '../components/Proof';
import ProblemSection from '../components/ProblemSection';
import Loop from '../components/Loop';
import CodeSection from '../components/CodeSection';
import Features from '../components/Features';
import SocialProof from '../components/SocialProof';
import Pricing from '../components/Pricing';
import FinalCTA from '../components/FinalCTA';

export default function HomePage() {
  return (
    <>
      <Hero />
      <Proof />
      <ProblemSection />
      <Loop />
      <CodeSection />
      <Features />
      <SocialProof />
      <Pricing />
      <FinalCTA />
    </>
  );
}
