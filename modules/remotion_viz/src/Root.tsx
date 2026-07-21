import { Composition } from "remotion";
import { FinancialCards } from "./FinancialCards";
import cardsData from "../public/cards.json";

export const RemotionRoot = () => {
  const { cards, totalDuration, totalFrames: fromJson, height: vizHeight } = cardsData;
  const totalFrames = fromJson || (cards[cards.length - 1]?.endFrame ?? 0) + 10 || 900;

  return (
    <Composition
      id="FinancialCards"
      component={FinancialCards}
      durationInFrames={totalFrames}
      fps={30}
      width={1080}
      height={vizHeight || 480}
      defaultProps={{ cards, totalDuration }}
    />
  );
};
